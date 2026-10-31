# Mobile Banking Frontend

A small React app that connects to the Flask API in this repository.

## Run locally

1. Start the API:
   ```bash
   cd ..
   export API_SIGNING_KEY="$(openssl rand -hex 32)"
   export ALLOW_DEMO_ATTESTATION=1
   python -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   flask --app app run --debug
   ```

2. In a second terminal, start the frontend:
   ```bash
   cd frontend
   npm install
   cp .env.example .env
   npm run dev
   ```

3. Open http://localhost:3000

If port 3000 is already in use, Vite automatically starts on the next available port and prints the URL. To choose a port explicitly, set `PORT` when starting the frontend, for example `PORT=3001 npm run dev`.

## Notes

- The frontend registers a demo ECDSA device and calls the backend’s `/v1/devices`, `/v1/auth/token`, `/v1/accounts`, `/v1/beneficiaries`, and `/v1/payments` endpoints.
- The demo username/password/OTP is the same one used by the backend tests:
  - alice / StrongPass!123 / 123456
