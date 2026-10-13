# 🚀 AI Agent Gateway

A production-grade, multi-tenant API gateway designed to securely route, authenticate, and rate-limit LLM traffic. 

Built to solve the core infrastructure challenges of deploying AI agents at scale: protecting root API keys, enforcing departmental token budgets, and containerizing backend services for cloud deployment.

## 🏗️ Architecture & Tech Stack
- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL (Serverless via Neon)
- **ORM:** SQLAlchemy + Psycopg 3
- **Containerization:** Docker
- **Cloud Infrastructure:** AWS EC2 (Ubuntu 26.04 LTS)
- **LLM Integration:** OpenAI API (`gpt-4o-mini`)

## ✨ Key Features
1. **Multi-Tenant Security:** Intercepts incoming requests and validates custom generated `sk-gateway-*` API keys before forwarding traffic to OpenAI.
2. **Real-Time Token Economics:** Dynamically tracks prompt and completion tokens for every request and deducts them from specific departmental budgets.
3. **Budget Guardrails:** Automatically blocks requests (403 Forbidden) if a tenant exceeds their allotted token budget, preventing runaway LLM costs.
4. **Cloud-Native:** Fully containerized via Docker for seamless deployment across local environments and AWS EC2.

## 🗄️ Database Schema
The system utilizes a serverless PostgreSQL database to manage state across distributed gateway nodes.
* `id`: Primary Key
* `name`: Department/Tenant Name (e.g., "Marketing", "Sales")
* `api_key`: Securely generated unique access token
* `token_budget`: Integer tracking remaining token allocation

## 🚀 Quick Start (Local Development)

**1. Clone and Install**
```bash
git clone [https://github.com/YourUsername/ai-agent-gateway.git](https://github.com/YourUsername/ai-agent-gateway.git)
cd ai-agent-gateway
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
