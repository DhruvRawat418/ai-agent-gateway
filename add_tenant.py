from database import SessionLocal, Tenant
import secrets

def create_tenant(name: str, budget: int = 10000):
    db = SessionLocal()
    
    # Generate a random API key for this specific tenant
    new_api_key = f"sk-gateway-{secrets.token_hex(16)}"
    
    new_tenant = Tenant(name=name, api_key=new_api_key, token_budget=budget)
    db.add(new_tenant)
    db.commit()
    db.refresh(new_tenant)
    
    print(f"Success! Created Tenant: {new_tenant.name}")
    print(f"Their custom API Key is: {new_tenant.api_key}")
    print(f"Starting Budget: {new_tenant.token_budget} tokens")
    
    db.close()

if __name__ == "__main__":
    create_tenant("Marketing Department")
