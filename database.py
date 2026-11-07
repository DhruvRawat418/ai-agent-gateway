import os
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Get the database URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# Connect to the Neon PostgreSQL database
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Define the Tenant (Client/Department) Schema
class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    api_key = Column(String, unique=True, index=True)
    token_budget = Column(Integer, default=10000)  # Default budget of 10,000 tokens

# Create the tables in the database
def init_db():
    Base.metadata.create_all(bind=engine)

# Only usage after dashboard installation is available; existing balances are preserved.
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, BigInteger

class UsageRecord(Base):
    __tablename__ = "gateway_usage"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    tokens = Column(BigInteger, nullable=False)
    model = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class RequestCost(Base):
    """Additive table: legacy usage rows remain untouched and unpriced."""
    __tablename__ = "gateway_request_costs"
    usage_id = Column(Integer, ForeignKey("gateway_usage.id"), primary_key=True)
    input_tokens = Column(BigInteger, nullable=True)
    output_tokens = Column(BigInteger, nullable=True)
    cached_tokens = Column(BigInteger, nullable=True)
    cost_nano_usd = Column(BigInteger, nullable=True)
    input_rate = Column(BigInteger, nullable=True)  # nanodollars per token
    output_rate = Column(BigInteger, nullable=True)
    cached_rate = Column(BigInteger, nullable=True)
    pricing_version = Column(String, nullable=True)
    reason = Column(String, nullable=True)

class RequestAttempt(Base):
    __tablename__ = "gateway_request_attempts"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    usage_id = Column(Integer, ForeignKey("gateway_usage.id"), nullable=True, unique=True)
    model = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    latency_ms = Column(BigInteger, nullable=False)
    error_code = Column(String, nullable=True)
    error_detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
