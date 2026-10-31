# Architecture

PesaAI is a small two-tier app: a React single-page frontend and a Flask JSON
API. External services are PayPal (sandbox) and OpenAI. Everything degrades
gracefully when a key is missing.

```
  Browser (React + AG Grid)
        |  fetch VITE_API_URL
        v
  Flask API (app.py)
        |                    \
        v                     v
  PayPal REST (sandbox)    OpenAI (gpt-4o-mini)
  - Orders v2 (top-up)     - chat completions (insights, chat)
  - Payouts v1 (agent)     - function calling (payment proposals)
```

## Backend endpoints (`app.py`)

| Method + path | Purpose |
|---------------|---------|
| `GET /health`, `GET /api/health` | Report real status: `paypal` and `ai` are `live` when keys are set, else `mock` |
| `GET /api/transactions` | The persisted ledger plus an income/spent/net summary |
| `POST /api/paypal/create-order` | Create a sandbox order, returns the payer `approve_url` |
| `POST /api/paypal/capture/<order_id>` | Capture an approved order, records a top-up in the ledger |
| `POST /api/paypal/execute` | Execute a confirmed agent payment via Payouts (guardrails + idempotency) |
| `POST /api/ai/insights` | Analyse the ledger, EN or SW |
| `POST /api/ai/chat` | Money-coach chat, EN or SW |
| `POST /api/ai/agent` | Agentic brain: returns either a coaching message or a payment proposal |
| `POST /api/ai/nudge` | Proactive coaching: finds a pattern in the ledger and may propose an action |

## The agentic commerce flow

This is the core, and it is deliberately split so that the model never moves
money by itself.

```
User: "send $15 to jane@example.com for the logo"
   |
   v
POST /api/ai/agent
   |  OpenAI with the propose_payment tool (tool_choice=auto)
   |  -> model decides: is this a payment request?
   v
  { type: "proposal", action: { amount, recipient, reason } }   # NO money moved
   |
   v
Frontend renders a "Confirm payment" card
   |
   | user clicks Confirm  (human in the loop)
   v
POST /api/paypal/execute
   |  server guardrails: amount > 0, amount <= MAX_AGENT_PAYMENT_USD, recipient present
   |  -> PayPal Payouts v1
   v
  { batch_id, status, mode: "live" }  -> ledger row appended
```

Key property: `/api/ai/agent` decides and proposes; `/api/paypal/execute` is the
only path that moves money, and it is reached only after an explicit user
confirmation in the UI. The model cannot call it directly.

## Graceful degradation

- **No PayPal keys:** money endpoints return a clearly labelled `mode: "mock"`
  response so the UI still demonstrates the flow.
- **No OpenAI key:** AI endpoints return `used_ai: false` with an honest
  computed summary (insights) or a canned tip (chat/agent), and the UI says a
  key is needed for real AI.

The frontend reads `/health` on load and shows live PayPal / AI status chips, so
a viewer can see which mode is active.

## Persistence (`db.py`)

SQLite via the stdlib `sqlite3`, so there is no extra dependency and nothing to
provision. On first use the database file is created and the ledger is seeded.
Three tables:

- `transactions` the ledger (date, description, amount, type, method, `sim`
  flag for illustrative rows).
- `idempotency` maps an `Idempotency-Key` to the stored response.
- `orders` the amount an order was created for, plus a `captured` flag, so
  capture can use a trusted amount and record each order only once.

Top-ups (capture) and agent payouts (execute) write to the ledger, so the
dashboard survives a reload. `DATABASE_PATH` controls the file location (default
is alongside the app; point it at a mounted disk for durability across deploys).

## Proactive coaching

`/api/ai/nudge` runs deterministic pattern detection over the ledger (small
repeated top-ups implying fees; a healthy surplus) using real numbers, then has
the model phrase the tip. When it finds a savings opportunity it returns a
`proposal` with an action, which flows through the same confirm gate as the
agent, so a proactive suggestion still never moves money on its own.

## Security

- Secrets only in env vars; `.env` is gitignored, `.env.example` holds
  placeholders only.
- Payment ceiling: `MAX_AGENT_PAYMENT_USD` (default 500) bounds every agent
  payment.
- Confirmation gate: no money moves without a user click.
- Idempotency: `/api/paypal/execute` dedupes by `Idempotency-Key`, so a repeated
  or retried confirm cannot double-send.
- Ledger integrity on capture: the top-up amount is taken from the verified
  PayPal capture response (or the amount stored when the order was created),
  never from the client's capture request, and each order is recorded at most
  once. A client cannot inflate the ledger or double-record by replaying a
  capture.
- CORS is open for the demo (read-only/idempotent endpoints, sandbox only); it
  would be tightened to known origins for production.

## Notable implementation choices

- Deployed via gunicorn as `app:app` (a module-level Flask app), matching the
  Dockerfile. No app factory, to keep the surface small.
- AG Grid v36 uses the new Theming API (`themeQuartz`) and explicit
  `ModuleRegistry.registerModules([AllCommunityModule])`, required on v36.
- OpenAI client is built lazily so the app imports and serves even with no key.
