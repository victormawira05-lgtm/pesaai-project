PesaAi

## Elevator pitch 
PesaAI is an AI money coach for Kenyan freelancers paid in USD via PayPal, that
explains your money and can send PayPal payments on command, after you confirm.

## Inspiration
Millions of Kenyans earn online through PayPal (Upwork, Fiverr, remote clients)
but live and spend locally. Managing money across that gap is painful: fees pile
up on small transfers, USD income is lumpy, and good financial advice is scarce.
We wanted to see what happens when you put an AI agent on top of PayPal's rails,
so money management becomes a conversation, not a spreadsheet.

## What it does
- Shows income, spending, and net on a clean dashboard (AG Grid ledger).
- Acts as a money coach in English or Swahili, by text or voice, grounded in
  your transactions.
- Runs agentic payments: say "send $15 to jane@example.com for the logo" and it
  proposes the payment, you confirm, and it completes via PayPal. It never sends
  without confirmation, payments are capped, and a repeated confirm is
  idempotent (no double-send).
- Coaches proactively: on load it reviews your ledger and suggests an action
  (for example moving a surplus to savings), which you can confirm in one click.
- Lets you top up via a real PayPal sandbox checkout. Your ledger is persisted
  (SQLite), so activity survives a reload.

## How we built it
- Backend: Python + Flask. PayPal REST v2 (Orders for top-ups, Payouts for the
  agent's "send money"). OpenAI `gpt-4o-mini`, with function calling so the model
  returns a structured, confirm-gated payment proposal rather than free text.
  SQLite (stdlib) persists the ledger with no external database to provision.
- Frontend: React + Vite + AG Grid (v36 Theming API).
- Hosting: Render, defined as Infrastructure as Code in `render.yaml`.

## How we use PayPal
OAuth2 client-credentials auth; Orders v2 create + capture (top-up flow);
Payouts v1 (agent-initiated send money). All on the sandbox.

## How we use AI
`gpt-4o-mini` chat completions power insights and the EN/SW coach. A
`propose_payment` function-calling tool lets the agent decide when a message is a
payment request and extract amount, recipient, and reason, which the UI turns
into a confirmation card. Money only moves after the user confirms.

## Challenges
- Keeping the agent safe: the model proposes, a separate confirmed endpoint
  executes, bounded by a server-side ceiling and idempotency so a confirm cannot
  double-send.
- Ledger integrity: amounts are taken from the verified PayPal capture, never
  the client, and each order is recorded once, so the ledger cannot be inflated.
- Being honest about what is real (PayPal sandbox, AI) vs illustrative (the
  M-Pesa sample rows), rather than faking a demo.

## What we learned
Agentic commerce is most compelling when the human stays in the loop: a single
confirm step makes an AI that spends money feel trustworthy instead of scary.

## What's next
Real M-Pesa (Daraja) integration; persistent accounts; recurring-payment
automations; multi-step agent plans ("pay rent and move the rest to savings").

## Categories we are entering
- Best Use of PayPal + AI
- Best Use of Agentic Commerce
- Best Use of AG Grid
- Best Use of Render

## Notes for judges (do not make public)
- PayPal sandbox buyer for the top-up flow: <add buyer email + password here>
- The backend is on Render free tier; allow ~20-30s for the first request.

## Links
- Repo:https://github.com/victormawira05-lgtm/pesaai-project
- App: https://pesaai-project-1.onrender.com
- API:https://pesaai-project.onrender.com/api/health
- Demo video: https://youtu.be/QzsEKFjHCdc
