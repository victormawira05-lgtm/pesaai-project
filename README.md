
PesaAI, what is done so far:
- Real PayPal sandbox: Orders (top-up: create, approve, capture) + Payouts
- Real AI coach (OpenAI gpt-4o-mini): spending insights and EN/SW chat, by text or voice
- Agentic payments: type "send $15 to jane@..." and it proposes, you confirm, it sends. Capped at $500, idempotent (no double send)
- Proactive coach: on load it suggests moving a surplus to savings
- SQLite persistence, AG Grid dashboard, clean and honest UI
- Security hardened: ledger amounts come from the verified PayPal capture, not the client
- 23 automated tests passing; README, ARCHITECTURE, Devpost draft, video script and render.yaml (deploy blueprint) all included
