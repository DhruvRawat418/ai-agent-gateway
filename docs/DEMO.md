# Three-minute demo and portfolio notes

## Demo sequence

1. **Problem (20 seconds):** “Teams want to use AI, while administrators need visibility and budget controls. This gateway connects department identity, token allocations, and request-level cost estimates.”
2. **Onboard (35 seconds):** Unlock privately, create a demo department with a small allocation, and explain that its key calls the API but cannot administer other departments. Keep keys out of the recording.
3. **Use (40 seconds):** Send a support-ticket classification through the gateway. Show recorded input/output tokens, latency, remaining balance, and known estimated cost. A prepared recording can avoid paid calls during interviews.
4. **Control (35 seconds):** Edit the allocation, showing usage preserved. Explain total allocation versus additional top-up.
5. **Evidence (30 seconds):** Show the recorded AWS concurrency trial: allocation 100, successful usage 37, remaining 63, and a blocked competing request. Open request history for status detail; department request counts include successes only.
6. **Tradeoff (20 seconds):** “A row lock makes the accounting easy to reason about, but serializes each department. The next engineering step is durable reservations and reconciliation, paired with staff accounts and key rotation.”

This is an administrator-controlled pilot, not an anonymous playground. Do not share the admin key with recruiters; use a video or guided demo. Stop screen sharing before retrieving any secret. Label screenshots/recordings with their capture date and distinguish synthetic data from real pilot requests.

## Portfolio positioning

**One-line description:** A departmental AI gateway that lets staff allocate token budgets, observe usage and estimated spend, and block requests that do not fit available headroom.

**Resume draft:** Built and deployed a FastAPI AI usage gateway on AWS EC2 with Neon PostgreSQL and Caddy HTTPS; implemented departmental budgets, request telemetry, and token-based cost estimates, with 30 tests including PostgreSQL lock contention and a deployed two-request validation.

**PM discussion:** Explain the administrator persona, the problem hypothesis, success metrics you would collect, and why cost visibility and predictable limits came before more model integrations.

**Product marketing discussion:** Frame the benefit as visibility and control over departmental AI usage. Treat “reduced costs” or “faster onboarding” as hypotheses until measured; do not claim savings or adoption from this pilot.

**FDE discussion:** Walk through bearer auth, the tenant lock, the provider call, atomic accounting, and an ambiguous timeout. Explain the Neon/EC2 integration and what remains untested at load.

## Evidence to collect next

- A screenshot of the HTTPS dashboard without credentials.
- A request-history screenshot showing successful and blocked attempts.
- A short recording of allocation changes preserving usage.
- Feedback from two prospective administrators and the resulting priority changes.

Do not invent users, savings percentages, uptime, or throughput. Current measured evidence is in README.md.
