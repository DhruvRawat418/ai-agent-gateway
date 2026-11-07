# Department dashboard

The dashboard is served by the existing FastAPI application at `/`. It uses the same PostgreSQL database as `/v1/chat`.

## Run locally

From your existing **AI Agent Gateway** folder:

1. Activate the environment: `source venv/bin/activate`
2. Generate a staff key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
3. Add `ADMIN_API_KEY=<generated-key>` to your existing `.env`. Keep your existing database URL and OpenAI key. Never commit `.env`.
4. Initialize the additional usage table: `python3 -c "from database import init_db; init_db()"`. Existing departments and remaining balances are preserved.
5. Start: `uvicorn main:app --reload`
6. Open http://127.0.0.1:8000 and enter the staff key.

Staff can create departments, copy each new department API key once, change total token allocations, search departments, filter departments needing attention, and monitor token usage. Data refreshes every 15 seconds while the page is visible. Staff credentials stay in browser memory and are cleared on lock or reload. Use HTTPS if hosting outside localhost. This first version uses one shared staff secret; it does not provide individual staff accounts or an audit trail of staff actions.

## Budget meaning and existing data

- **Used:** successful requests recorded in `gateway_usage` after this upgrade.
- **Remaining:** the existing `tenants.token_budget` value.
- **Allocated:** used + remaining.
- Changing an allocation adjusts remaining tokens while preserving recorded usage. For example, 2,000 used with a new allocation of 10,000 leaves 8,000 remaining.
- An allocation cannot be reduced below usage already recorded. Set it equal to usage to stop further requests.
- Old usage cannot be reconstructed from the previous remaining-only schema. Existing balances become the initial allocation; no historical usage is invented.
- Budgets have no monthly reset in this version. “Low balance” means at least 80% used; zero/negative balance is exhausted.
- The gateway checks a conservative prompt allowance before dispatch and limits generated tokens to the remaining balance minus that allowance. PostgreSQL row locks serialize department requests and budget edits; one provider request is in flight per department. Only actual returned usage is charged. This is not an absolute provider billing guarantee: a timeout, process crash, or database failure may leave provider charges unrecorded.

## Checks

`python3 -m unittest discover -s tests -v`

The tests use an isolated SQLite database and a mocked provider, with no real provider requests. PostgreSQL lock behavior needs separate integration testing.

## Deployment

Deploy the updated Python files and `static/` together. Run table initialization once against the deployment database before starting the upgraded app. Pass runtime secrets into Docker with `--env-file .env`; `.env` is deliberately excluded from the image. The hosted pilot was subsequently deployed on EC2 with Neon and Caddy HTTPS. See docs/DEPLOYMENT.md for current operations; this documentation update does not push to GitHub.

## Usage history

The daily chart and request history share a department filter and a 7/30-day period selector. Periods include the current Eastern calendar day; history timestamps and daily boundaries use America/New_York, automatically switching between EST and EDT. Stored timestamps remain UTC. Empty days are zero-filled. The table displays 20 requests per page, newest first, with request ID as a stable tie breaker. The usage chart includes successful recorded requests; the activity table also includes blocked and failed authenticated attempts. Prompts, responses, and credentials are not returned.

This feature uses the existing gateway_usage table; no additional migration is required. Restart FastAPI if not using --reload, then refresh the browser. The existing 15-second refresh also updates history while retaining its filters and current page.

Validation uses isolated SQLite data and a mocked provider; PostgreSQL date grouping uses explicit America/New_York conversion and has not been integration-tested against the live database.

## Estimated dollar costs

On startup the application creates the additive `gateway_request_costs` table if absent. Existing usage and budgets are not rewritten. The database role needs permission to create this table; alternatively run `python3 -c "from database import init_db; init_db()"` using your migration role before restart.

New requests record provider-reported input, output and cached input token counts, along with the resolved model, integer nanodollar cost, rate snapshot and pricing version. Usage and cost are committed in the same transaction. Cached tokens are part of input, not extra tokens. Costs use `(input - cached) × input rate + cached × cached rate + output × output rate`.

Supported prices: GPT-4o mini and its exact 2024-07-18 snapshot, standard text tier. As checked November 5, 2026, USD per million tokens: input $0.15, cached input $0.075, output $0.60. Source: https://developers.openai.com/api/docs/models/gpt-4o-mini . Rates live in pricing.py; review and update them as provider prices change. Saved historical estimates retain their original rates.

Unknown models, unknown service tiers and missing/inconsistent token breakdowns are unpriced. Legacy records are also unpriced because only total tokens were stored. Totals include priced records only and display coverage; unpriced does not mean free. No usage is fabricated or backfilled. These are estimates, not invoices: taxes, credits, negotiated rates and unrecorded/failed provider calls are excluded. Token budget enforcement remains token-based. The chart remains a token chart; the filtered cost total is displayed above it. Dollar values show up to six decimals so small requests do not appear free.

Validation: 17 unit tests using SQLite/mock provider, plus browser checks of mixed legacy/priced history and department filtering. No paid provider requests were made during development; live PostgreSQL integration remains to be verified after restart.

## Request reliability

Startup creates the additive gateway_request_attempts table if absent. New authenticated requests record successful, budget-blocked, provider-error, or recording-error status plus processing latency. Old usage appears once as successful with unknown latency; no historical attempts are invented. Missing/invalid department keys and payload-validation errors are not attributed or logged. Database authentication-query failures and process crashes are not covered.

History uses /api/admin/activity and supports status and slow-only (at least 5,000 ms) filters. Department and Eastern date range affect both history and the usage chart; status/slow filters affect history only. Success, blocked and error counts describe the selected department/period before status/slow filtering. Page size is 20. Usage and estimated spend still include successful recorded requests only. Failed calls show unknown cost; budget-blocked calls are marked not sent.

Latency is elapsed gateway handling time through provider completion or failure, including department row-lock waits and provider time, but excluding final telemetry commit. New calls disable SDK retries and use a 30-second SDK timeout. No prompts, responses, keys, raw provider errors, or raw database errors are stored in attempts. Safe error codes map to fixed descriptions.

Success usage, cost, balance and attempt commit together. Provider failures roll back and then log separately. If a response arrives but cannot be recorded, rollback preserves the prior balance and attempts to log a recording error; provider charges may still apply. If logging also fails, a static server message is emitted and the original HTTP error is preserved. There is no durable external log or reconciliation queue yet.

Validation: 23 isolated SQLite/mock-provider tests, plus browser checks of provider-error, slow-only and budget-blocked filters. No paid requests were made in these checks. PostgreSQL budget-lock integration was subsequently verified; see the budget checks section below.


## Prompt-aware budget checks

For the current text-only GPT-4o mini pilot, supported request models are `gpt-4o-mini` and `gpt-4o-mini-2024-07-18`. Other models return validation error 422 until a model policy is added. Prompts are limited to 100,000 characters. Optional `max_completion_tokens` accepts integer values 1–16,384 and defaults to 1,024. The gateway can reduce it further; the response includes `completion_token_limit` and provider `finish_reason` (`length` means output reached a limit).

The input allowance is UTF-8 byte length plus 64 tokens of message-framing headroom. It is intentionally conservative, not exact tokenization; some prompts are rejected even if their true token count would fit. Output is capped to the lesser of the requested limit, remaining budget minus the allowance, and the model's 128,000-token context minus the allowance. Checks run while holding the PostgreSQL tenant row lock. A rejected request returns 403, records a blocked attempt, and does not contact the provider. Unused allowance is never charged. Provider calls use a 30-second SDK timeout and no automatic retries. Timeouts do not prove that no provider charge occurred; reconciliation remains future work. The database row lock can wait longer than the provider timeout.

Actual provider usage remains authoritative, even if it unexpectedly exceeds the estimate: do not clamp usage or hide a negative balance. This policy is a conservative guardrail, not a guarantee against all billing discrepancies.

API reference: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create

Validation for budget checks (2026-11-05): all 30 tests pass, including the opt-in concurrency test against an isolated PostgreSQL 16 Docker container. The test observes pg_blocking_pids to prove the second request waits on the first transaction. Starting from 100 tokens, the first mocked response records 90 tokens; the second request then returns 403, with one provider invocation, one usage record, and 10 tokens remaining. No paid model calls or existing department data are used. To run it, set GATEWAY_TEST_POSTGRES_URL to a disposable PostgreSQL database and run `python -m unittest discover -s tests -v`. The test creates and drops a uniquely named schema; never point it at production. SQLite checks do not verify PostgreSQL row locks.


## Hosted validation update

On November 5, 2026, the EC2 image passed 29 tests with the optional PostgreSQL integration test skipped. A separate live AWS/Neon trial sent two concurrent requests against a new 100-token department: one succeeded with 37 tokens, one returned 403, and the dashboard showed 63 remaining. This is a single deployed trial, not direct lock instrumentation or a load test. HTTPS and removal of public TCP 8000 access were verified by the operator. Earlier validation notes above describe their respective implementation stages.
