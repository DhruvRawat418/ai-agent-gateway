from database import SessionLocal, Tenant

db = SessionLocal()
tenants = db.query(Tenant).all()

print("\n--- LIVE TENANT BUDGETS ---")
for t in tenants:
    print(f"Department: {t.name}")
    print(f"Remaining Tokens: {t.token_budget}")
    print("-" * 25)
    
db.close()
