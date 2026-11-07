# Architecture and accounting

FastAPI serves static HTML/CSS/JavaScript and the JSON API. Caddy terminates HTTPS on the EC2 host and proxies to the Docker-published gateway port. Neon stores department identity, balances, and telemetry. DuckDNS supplies the hostname; an optional host-side systemd timer keeps its IPv4 record current through IMDSv2.

## Request lifecycle

```mermaid
sequenceDiagram
    participant Client as Department client
    participant API as FastAPI
    participant DB as PostgreSQL
    participant Provider as OpenAI
    Client->>API: POST /v1/chat + department key
    API->>DB: SELECT tenant FOR UPDATE
    Note over API,DB: Same-department calls and budget edits wait
    alt Prompt allowance cannot fit
        API->>DB: Record blocked attempt; commit
        API-->>Client: 403, no provider call
    else Sufficient headroom
        API->>Provider: Prompt + capped max_completion_tokens
        Provider-->>API: Text, resolved model, token usage
        API->>DB: Deduct usage; save usage, cost, attempt; commit
        API-->>Client: Response + usage + remaining budget
    end
```

`tenants.token_budget` is the remaining balance. Displayed total allocation is recorded successful usage plus remaining. Updating an allocation sets remaining to new allocation minus recorded usage; lowering it below recorded usage is rejected. No historical consumption is fabricated during schema upgrades.

`gateway_usage` holds successful token totals; `gateway_request_costs` holds token breakdowns, nanodollar cost, and rate/version snapshots; `gateway_request_attempts` records status and latency. Successful records share one commit with the balance update. Provider failures roll back, then attempt a separate error log. Request telemetry does not persist prompts or responses.

## What the lock guarantees—and what it does not

The lock prevents two transactions from reading and spending the same department balance concurrently. Different departments can proceed independently. Holding a transaction while waiting on a network call increases connection pressure and per-department latency; production capacity needs measurement.

The input allowance is conservative. We cap output based on it and account for actual usage afterward. Actual usage is never clamped to hide overages. A provider might charge a request whose outcome was lost during a timeout or process/database failure; row locks cannot reconcile that external charge. Durable reservations and reconciliation would be a separate design.

## Trust boundaries

Staff and department credentials serve different endpoints. Browser staff credentials stay in memory. The database currently contains plaintext department keys, so database access is credential access. HTTPS protects browser-to-server transport; the EC2 security group blocks direct public TCP 8000. The Docker port remains published on the host; binding it to loopback is a future defense-in-depth change.

No claims are made about independently audited security, SLA, business savings, production scale, or tenant-specific data isolation beyond the implemented gateway identity/accounting paths.
