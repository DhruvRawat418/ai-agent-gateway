import os
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from database import SessionLocal, Tenant

load_dotenv()

app = FastAPI(title="AI Agent Gateway")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
security = HTTPBearer()

# Database connection dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class ChatRequest(BaseModel):
    model: str = "gpt-4o-mini"
    prompt: str

@app.post("/v1/chat")
async def proxy_chat(
    request: ChatRequest, 
    credentials: HTTPAuthorizationCredentials = Security(security),
    db = Depends(get_db)
):
    # 1. Authenticate the Tenant
    provided_key = credentials.credentials
    tenant = db.query(Tenant).filter(Tenant.api_key == provided_key).first()
    
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid Gateway API Key")
        
    # 2. Check their token budget
    if tenant.token_budget <= 0:
        raise HTTPException(status_code=403, detail="Token budget exceeded. Please recharge.")

    try:
        # 3. Forward request to OpenAI
        response = client.chat.completions.create(
            model=request.model,
            messages=[{"role": "user", "content": request.prompt}]
        )
        
        reply = response.choices[0].message.content
        total_tokens = response.usage.total_tokens
        
        # 4. Deduct tokens and save to the database
        tenant.token_budget -= total_tokens
        db.commit()
        
        return {
            "response": reply,
            "tenant_authenticated": tenant.name,
            "tokens_used": total_tokens,
            "remaining_budget": tenant.token_budget
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
