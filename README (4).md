# PesaAI 🇰🇪

**An AI money coach for Kenyan freelancers who earn in USD via PayPal and spend
locally.** PesaAI explains your money in English or Swahili, flags fees and
waste, and can carry out PayPal payments on command, always after you confirm.

Built for the [PayPal AI Hackathon](https://paypalaihackathon.devpost.com/).

## Live demo

- **App (frontend):** https://pesaai-project-ai.onrender.com/
- **API (backend):** https://pesaai-backend-fixed.onrender.com/
> Render's free tier sleeps when idle, so the first request can take 20-30
> seconds to wake the backend. After that it responds normally.

## What it does

1. **Dashboard.** Your income, spending, and net, with a filterable AG Grid
   ledger (pinned totals, category pills).
2. **AI coach.** Ask about your money in English or Swahili, by typing or by
   voice. It gives short, practical answers grounded in your actual transactions.
3. **Agentic payments.** Tell the coach *"send $15 to jane@example.com for the
   logo"*. It proposes the payment, you confirm, and only then does it move
   sandbox money through PayPal. Nothing is ever sent without your confirmation,
   agent payments are capped (default $500), and a repeated confirm is
   idempotent so you cannot double-send.
4. **Proactive coaching.** On load, the coach reviews your ledger and, when it
   spots an opportunity (for example a healthy surplus), proactively suggests an
   action, such as moving part of it to savings, which you can confirm in one
   click.
5. **PayPal top-ups.** Add funds through a real PayPal sandbox checkout
   (create, approve, capture).

Your ledger is persisted in SQLite, so top-ups and payments survive a reload.

## What is real vs illustrative

We are deliberate about this so judges are never misled:

- **PayPal is a real sandbox integration.** Orders and payouts go through
  PayPal's live sandbox REST API. No real money moves.
- **AI is real.** Insights, chat, and the payment agent call OpenAI
  (`gpt-4o-mini`). When no key is configured, the app says so and falls back to
  an honest, clearly labelled non-AI summary rather than faking a response.
- **M-Pesa figures are illustrative sample data** (rows tagged `sim`), included
  to tell the Kenyan freelancer story. There is no live M-Pesa integration.

## How judges test it

No login required.

1. Open the app link above (give the backend a moment to wake). The coach
   greets you and, on load, proactively suggests a savings action you can
   confirm.
2. **AI insights:** click **Insights**. The coach analyses the sample ledger.
3. **Chat:** ask a question, e.g. "How do I cut my fees?" Toggle **SW** for
   Swahili, or use the microphone button to speak (where the browser supports it).
4. **Agentic payment:** type `send $15 to jane@example.com for design work`.
   Review the confirmation card, click **Confirm & send**, and watch the payout
   complete and a new row appear.
5. **PayPal top-up:** enter an amount and click **Pay with PayPal**, approve in
   the PayPal sandbox window, then **Complete top-up**.

A PayPal sandbox buyer account for the top-up flow is provided in the Devpost
submission notes (not committed to this public repo).

## Tech stack

- **Backend:** Python, Flask, SQLite (stdlib, zero-config), PayPal REST v2
  (Orders + Payouts, sandbox), OpenAI (`gpt-4o-mini`) with function calling
- **Frontend:** React, Vite, AG Grid (v36 Theming API), Web Speech API for voice
- **Hosting:** Render (Infrastructure as Code via `render.yaml`)

## AI tools used, and how

| Tool | How it is used |
|------|----------------|
| OpenAI `gpt-4o-mini`, chat completions | Transaction insights and the bilingual (EN/SW) coach chat |
| OpenAI function calling (`propose_payment` tool) | The agent reads a free-text request, decides whether it is a payment, and returns a structured, confirm-gated proposal |

## PayPal features used

- OAuth2 client-credentials token
- Orders v2: create order, capture order (the top-up flow)
- Payouts v1: send money to a recipient (the agent "send money" flow)

## Local setup

**Backend**
```bash
cp .env.example .env     # add PayPal sandbox + OpenAI keys
pip install -r requirements.txt
python app.py            # serves on :8000  (or: gunicorn app:app --bind 0.0.0.0:8000)
```

**Frontend**
```bash
cd frontend
cp .env.example .env     # set VITE_API_URL (default points at the deployed backend)
npm install
npm run dev              # serves on :3000
```

**Tests**
```bash
pip install pytest
pytest                   # external services are mocked, runs offline
```

## Deployment

Both services are defined as Infrastructure as Code in [`render.yaml`](render.yaml)
(a Render Blueprint): the Flask API as a web service (`gunicorn app:app`) and the
React app as a static site. Push the repo and create a Blueprint in Render, then
set the secrets (`PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `OPENAI_API_KEY`) in the
dashboard. SQLite needs no provisioning; see the comments in `render.yaml` for
the optional durable-disk upgrade.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for request flows, the agentic
confirmation gate, persistence, and security notes.

## Security notes

- Secrets live only in environment variables (`.env` locally, the host
  dashboard in production). Nothing secret is committed; see `.gitignore`.
- The payment agent never moves money without an explicit user confirmation,
  and every agent payment is bounded by a server-side ceiling.
- Payments are idempotent: a repeated or retried confirm cannot double-send.
- Ledger integrity: a top-up is recorded from the verified PayPal capture (or
  the amount the order was created for), never a client-supplied value, and each
  order is recorded at most once, so the ledger cannot be inflated or replayed.

## License

MIT, see [LICENSE](LICENSE).
