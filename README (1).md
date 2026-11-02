# PesaAI - Voice AI Money Coach for Kenyan Freelancers

Live: https://pesaai-project-1.onrender.com
API: https://pesaai-project.onrender.com
Video: https://youtu.be/QzsEKFjHCdc

Kenya has 5M+ freelancers paid in USD via PayPal, spending in KES via M-Pesa. PesaAI is a voice-enabled AI coach that turns PayPal income + M-Pesa spend into smart savings.

## Features (Hackathon Scoring)

- **PayPal API:** Orders + Payouts Sandbox, idempotency key, MOCK-PAYOUT-0FCE0066 SUCCESS mock mode
- **M-Pesa:** Illustrative sim data (Daraja sandbox unstable, marked transparently)
- **AI Coach:** Groq + fallback mock, analyzes $200 income vs $71.76 spend, proposes $32.06 savings
- **Voice AI:** 🎤 Web Speech API, EN + SW (sw-KE), auto-transcribe + TTS response + payout confirmation by voice
- **Proactive Nudge:** Save suggestion pop-up

## Tech Stack
React + AG Grid, Flask API, PayPal REST API, Groq AI, Web Speech API

## Run Locally

1. Backend:
```bash
cd backend
export API_SIGNING_KEY="$(openssl rand -hex 32)"
pip install -r requirements.txt
flask --app app run --debug
cd frontend
npm install
cp .env.example .env
# Set VITE_API_URL=https://pesaai-project.onrender.com in .env
npm run dev
