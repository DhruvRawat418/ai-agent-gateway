import os
import secrets
import time
import logging
from pathlib import Path
from typing import Literal
from datetime import timezone
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, literal, union_all
from sqlalchemy.exc import IntegrityError
from openai import OpenAI, APITimeoutError, APIConnectionError
from dotenv import load_dotenv
from database import SessionLocal, Tenant, UsageRecord, RequestCost, RequestAttempt, engine
from pricing import estimate, usd
from contextlib import asynccontextmanager

load_dotenv()
@asynccontextmanager
async def lifespan(app):
    # Idempotent additive migration; never rewrites existing usage or budgets.
    RequestCost.__table__.create(bind=engine, checkfirst=True)
    RequestAttempt.__table__.create(bind=engine, checkfirst=True)
    yield

app = FastAPI(title="AI Agent Gateway", lifespan=lifespan)
@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/admin"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

security = HTTPBearer(auto_error=False)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_staff(credentials: HTTPAuthorizationCredentials = Security(security)):
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        raise HTTPException(503, "Dashboard access is not configured. Set ADMIN_API_KEY on the server.")
    if not credentials or not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(401, "Invalid staff access key")

def get_provider():
    return None  # Construct only after authentication and budget checks.

class ChatRequest(BaseModel):
    # Budget policy currently covers these text-only models.
    model: Literal["gpt-4o-mini", "gpt-4o-mini-2024-07-18"] = "gpt-4o-mini"
    prompt: str = Field(min_length=1, max_length=100_000)
    max_completion_tokens: int = Field(default=1024, ge=1, le=16_384, strict=True)

class BudgetUpdate(BaseModel):
    total_budget: int = Field(ge=0, le=2_000_000_000, strict=True)

class DepartmentCreate(BudgetUpdate):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a department name")
        return value

def tokens_used(db, tenant_id):
    return int(db.query(func.coalesce(func.sum(UsageRecord.tokens), 0)).filter(UsageRecord.tenant_id == tenant_id).scalar())

def iso_date(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat() if value else None

@app.get("/api/admin/departments", dependencies=[Depends(require_staff)])
def departments(db=Depends(get_db)):
    # One joined query keeps the balance and usage snapshot consistent.
    usage = db.query(UsageRecord.tenant_id, func.sum(UsageRecord.tokens).label("used"), func.count(UsageRecord.id).label("requests"), func.max(UsageRecord.created_at).label("last_used"), func.sum(RequestCost.cost_nano_usd).label("cost"), func.count(RequestCost.cost_nano_usd).label("priced")).outerjoin(RequestCost, UsageRecord.id == RequestCost.usage_id).group_by(UsageRecord.tenant_id).subquery()
    rows = db.query(Tenant, usage.c.used, usage.c.requests, usage.c.last_used, usage.c.cost, usage.c.priced).outerjoin(usage, Tenant.id == usage.c.tenant_id).order_by(Tenant.name).all()
    return {"departments": [{"id": t.id, "name": t.name, "used": int(used or 0), "remaining": t.token_budget, "total_budget": t.token_budget + int(used or 0), "requests": int(count or 0), "last_used": iso_date(last), "estimated_cost_usd": usd(cost), "priced_requests": int(priced or 0), "unpriced_requests": int(count or 0)-int(priced or 0)} for t, used, count, last, cost, priced in rows], "tracking_since": iso_date(db.query(func.min(UsageRecord.created_at)).scalar())}

@app.post("/api/admin/departments", status_code=201, dependencies=[Depends(require_staff)])
def create_department(data: DepartmentCreate, db=Depends(get_db)):
    key = "sk-gateway-" + secrets.token_hex(16)
    tenant = Tenant(name=data.name, api_key=key, token_budget=data.total_budget)
    db.add(tenant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A department with that name already exists")
    return {"id": tenant.id, "name": tenant.name, "api_key": key}

@app.patch("/api/admin/departments/{tenant_id}/budget", dependencies=[Depends(require_staff)])
def update_budget(tenant_id: int, data: BudgetUpdate, db=Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).with_for_update().first()
    if tenant is None:
        raise HTTPException(404, "Department not found")
    used = tokens_used(db, tenant_id)
    if data.total_budget < used:
        raise HTTPException(422, f"Total allocation cannot be lower than the {used:,} tokens already used")
    tenant.token_budget = data.total_budget - used
    db.commit()
    return {"total_budget": data.total_budget, "used": used, "remaining": tenant.token_budget}

def elapsed_ms(started):
    return max(0, round((time.perf_counter() - started) * 1000))

def safe_provider_error(error):
    if isinstance(error, (APITimeoutError, TimeoutError)):
        return "provider_timeout", "The model provider timed out. Try again later.", 504
    if isinstance(error, APIConnectionError):
        return "provider_connection", "Could not connect to the model provider.", 502
    status = getattr(error, "status_code", None)
    if status == 429:
        return "provider_rate_limit", "The provider rate or quota limit was reached.", 502
    if status in (401, 403):
        return "provider_auth", "The provider rejected the gateway credentials or permissions.", 502
    if status in (400, 404, 422):
        return "provider_request", "The provider rejected the model or request settings.", 502
    return "provider_error", "The model provider could not complete the request.", 502

def record_failure(db, tenant_id, model, status, started, code, detail):
    # Best effort: when the DB itself is unavailable we cannot promise a durable log.
    try:
        db.add(RequestAttempt(tenant_id=tenant_id, model=model, status=status,
                              latency_ms=elapsed_ms(started), error_code=code, error_detail=detail))
        db.commit()
    except Exception:
        db.rollback()
        logging.getLogger("gateway").error("Request attempt could not be persisted")

@app.post("/v1/chat")
def proxy_chat(request: ChatRequest, credentials: HTTPAuthorizationCredentials = Security(security), db=Depends(get_db), client=Depends(get_provider)):
    started = time.perf_counter()
    if not credentials:
        raise HTTPException(401, "Missing Gateway API Key")
    tenant = db.query(Tenant).filter(Tenant.api_key == credentials.credentials).with_for_update().first()
    if not tenant:
        raise HTTPException(401, "Invalid Gateway API Key")
    tenant_id, tenant_name = tenant.id, tenant.name
    if tenant.token_budget <= 0:
        record_failure(db, tenant_id, request.model, "blocked", started, "budget_exhausted",
                       "Department token budget is exhausted. Increase its allocation to resume.")
        raise HTTPException(403, "Token budget exceeded. Please recharge.")
    # Deliberately conservative for a single text user message: UTF-8 bytes
    # plus framing headroom. This is an allowance, not a tokenizer count.
    input_allowance = len(request.prompt.encode("utf-8")) + 64
    completion_limit = min(request.max_completion_tokens,
                           tenant.token_budget - input_allowance,
                           128_000 - input_allowance)
    if completion_limit < 1:
        detail = "Not enough tokens for this prompt and a response. Shorten the prompt or increase the allocation."
        record_failure(db, tenant_id, request.model, "blocked", started,
                       "insufficient_prompt_budget", detail)
        raise HTTPException(403, detail)
    try:
        # Avoid automatic retries after ambiguous failures and bound lock duration.
        client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0, timeout=30.0)
        response = client.chat.completions.create(
            model=request.model, messages=[{"role": "user", "content": request.prompt}],
            max_completion_tokens=completion_limit)
    except Exception as error:
        db.rollback()
        code, detail, http_status = safe_provider_error(error)
        record_failure(db, tenant_id, request.model, "provider_error", started, code, detail)
        raise HTTPException(http_status, detail)
    try:
        total_tokens = response.usage.total_tokens
        tenant.token_budget -= total_tokens
        served_model = getattr(response, "model", None) or request.model
        record = UsageRecord(tenant_id=tenant_id, tokens=total_tokens, model=served_model)
        db.add(record)
        db.flush()
        cost = estimate(response)
        db.add(RequestCost(usage_id=record.id, **cost))
        duration = elapsed_ms(started)
        db.add(RequestAttempt(tenant_id=tenant_id, usage_id=record.id, model=served_model,
                              status="success", latency_ms=duration))
        result = {"response": response.choices[0].message.content, "tenant_authenticated": tenant_name,
                  "tokens_used": total_tokens, "remaining_budget": tenant.token_budget,
                  "estimated_cost_usd": usd(cost["cost_nano_usd"]), "cost_unavailable_reason": cost["reason"],
                  "latency_ms": duration, "completion_token_limit": completion_limit,
                  "finish_reason": getattr(response.choices[0], "finish_reason", None)}
        db.commit()
        return result
    except Exception:
        db.rollback()
        detail = "The provider returned a response, but the gateway could not record it. Provider charges may still apply."
        record_failure(db, tenant_id, request.model, "recording_error", started, "recording_error", detail)
        raise HTTPException(502, detail)

# Group usage by Eastern calendar days, including daylight-saving transitions.
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Annotated
from fastapi import Query

EASTERN = ZoneInfo("America/New_York")

def usage_window(now, days):
    local_today = now.astimezone(EASTERN).replace(hour=0, minute=0, second=0, microsecond=0)
    local_start = local_today - timedelta(days=days - 1)
    return local_start, local_start.astimezone(timezone.utc), (local_today + timedelta(days=1)).astimezone(timezone.utc)

def eastern_date(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(EASTERN).date().isoformat()

@app.get("/api/admin/usage", dependencies=[Depends(require_staff)])
def usage_history(
    days: Annotated[int, Query(ge=7, le=30)] = 7,
    department_id: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    db=Depends(get_db),
):
    if days not in (7, 30):
        raise HTTPException(422, "Period must be 7 or 30 days")
    local_start, start, end = usage_window(datetime.now(timezone.utc), days)
    if department_id is not None and db.get(Tenant, department_id) is None:
        raise HTTPException(404, "Department not found")
    conditions = [UsageRecord.created_at >= start, UsageRecord.created_at < end]
    if department_id is not None:
        conditions.append(UsageRecord.tenant_id == department_id)
    if db.bind.dialect.name == "sqlite":
        # SQLite has no IANA timezone support; use the same ZoneInfo conversion.
        db.connection().connection.driver_connection.create_function("gateway_eastern_date", 1, eastern_date)
        bucket = func.gateway_eastern_date(UsageRecord.created_at)
    else:
        bucket = func.date(func.timezone("America/New_York", UsageRecord.created_at))
    grouped = db.query(bucket, func.sum(UsageRecord.tokens), func.count(UsageRecord.id)).filter(*conditions).group_by(bucket).all()
    by_day = {str(day): (int(tokens), int(count)) for day, tokens, count in grouped}
    daily = []
    for offset in range(days):
        day = (local_start + timedelta(days=offset)).date().isoformat()
        tokens, count = by_day.get(day, (0, 0))
        daily.append({"date": day, "tokens": tokens, "requests": count})
    total_requests = sum(d["requests"] for d in daily)
    page_size = 20
    # Clamp pages after filters change or data is removed; stable order for equal timestamps.
    page = min(page, max(1, (total_requests + page_size - 1) // page_size))
    records = db.query(UsageRecord, Tenant.name, RequestCost).outerjoin(RequestCost, UsageRecord.id == RequestCost.usage_id).join(Tenant, Tenant.id == UsageRecord.tenant_id).filter(*conditions).order_by(UsageRecord.created_at.desc(), UsageRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    cost_total, priced = db.query(func.sum(RequestCost.cost_nano_usd), func.count(RequestCost.cost_nano_usd)).select_from(UsageRecord).outerjoin(RequestCost, UsageRecord.id == RequestCost.usage_id).filter(*conditions).one()
    return {
        "estimated_cost_usd": usd(cost_total), "priced_requests": priced, "unpriced_requests": total_requests-priced,
        "days": days, "timezone": "America/New_York", "daily": daily,
        "total_tokens": sum(d["tokens"] for d in daily), "total_requests": total_requests,
        "page": page, "page_size": page_size,
        "requests": [{"id": r.id, "department": name, "department_id": r.tenant_id, "model": r.model, "tokens": r.tokens, "created_at": iso_date(r.created_at), "input_tokens": c.input_tokens if c else None, "output_tokens": c.output_tokens if c else None, "cached_tokens": c.cached_tokens if c else None, "estimated_cost_usd": usd(c.cost_nano_usd) if c else None, "cost_unavailable_reason": c.reason if c else "Legacy request: token breakdown not recorded"} for r, name, c in records],
    }

@app.get("/api/admin/activity", dependencies=[Depends(require_staff)])
def request_activity(
    days: Annotated[int, Query(ge=7, le=30)] = 7,
    department_id: Annotated[int | None, Query(ge=1)] = None,
    page: Annotated[int, Query(ge=1, le=100000)] = 1,
    status: str = "all",
    slow_only: bool = False,
    db=Depends(get_db),
):
    if days not in (7, 30) or status not in ("all", "success", "blocked", "provider_error", "recording_error"):
        raise HTTPException(422, "Invalid activity filter")
    if department_id is not None and db.get(Tenant, department_id) is None:
        raise HTTPException(404, "Department not found")
    _, start, end = usage_window(datetime.now(timezone.utc), days)
    # Include old successful usage without inventing latency or duplicating new attempts.
    success = select(
        UsageRecord.id.label("id"), literal("usage").label("source"), UsageRecord.tenant_id.label("tenant_id"),
        UsageRecord.model.label("model"), UsageRecord.created_at.label("created_at"), literal("success").label("status"),
        RequestAttempt.latency_ms.label("latency_ms"), literal(None).label("error_code"), literal(None).label("error_detail"),
        UsageRecord.tokens.label("tokens"), RequestCost.input_tokens.label("input_tokens"), RequestCost.output_tokens.label("output_tokens"),
        RequestCost.cached_tokens.label("cached_tokens"), RequestCost.cost_nano_usd.label("cost"), RequestCost.reason.label("cost_reason")
    ).select_from(UsageRecord).outerjoin(RequestAttempt, RequestAttempt.usage_id == UsageRecord.id).outerjoin(RequestCost, RequestCost.usage_id == UsageRecord.id)
    failed = select(
        RequestAttempt.id, literal("attempt"), RequestAttempt.tenant_id, RequestAttempt.model, RequestAttempt.created_at,
        RequestAttempt.status, RequestAttempt.latency_ms, RequestAttempt.error_code, RequestAttempt.error_detail,
        literal(None), literal(None), literal(None), literal(None), literal(None), literal(None)
    ).where(RequestAttempt.usage_id.is_(None))
    events = union_all(success, failed).subquery()
    base = db.query(events, Tenant.name.label("department")).join(Tenant, Tenant.id == events.c.tenant_id).filter(events.c.created_at >= start, events.c.created_at < end)
    if department_id is not None:
        base = base.filter(events.c.tenant_id == department_id)
    counts = dict(db.query(events.c.status, func.count()).filter(events.c.created_at >= start, events.c.created_at < end,
        *([events.c.tenant_id == department_id] if department_id is not None else [])).group_by(events.c.status).all())
    if status != "all":
        base = base.filter(events.c.status == status)
    if slow_only:
        base = base.filter(events.c.latency_ms >= 5000)
    total = base.count()
    page_size = 20
    page = min(page, max(1, (total + page_size - 1)//page_size))
    rows = base.order_by(events.c.created_at.desc(), events.c.source, events.c.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"page":page, "page_size":page_size, "total_requests":total, "status_counts":counts, "slow_threshold_ms":5000,
        "requests":[{"id":f"{'U' if r.source == 'usage' else 'A'}-{r.id}", "department":r.department, "model":r.model,
            "created_at":iso_date(r.created_at), "status":r.status, "latency_ms":r.latency_ms,
            "error_code":r.error_code, "error_detail":r.error_detail, "tokens":r.tokens,
            "input_tokens":r.input_tokens, "output_tokens":r.output_tokens, "cached_tokens":r.cached_tokens,
            "estimated_cost_usd":usd(r.cost), "cost_unavailable_reason":r.cost_reason or ("Token breakdown not recorded" if r.status == "success" and r.cost is None else None)} for r in rows]}
