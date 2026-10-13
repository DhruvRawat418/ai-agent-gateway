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
