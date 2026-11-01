"""PesaAI backend.

An AI money coach for Kenyan freelancers who earn in USD via PayPal and spend
locally. The backend does three real things:

1. PayPal (sandbox): create, approve, and capture orders, and send payouts.
2. AI: explain transactions and chat as a money coach (OpenAI).
3. Agentic commerce: the AI proposes a PayPal payment, and only after the user
   confirms does the server actually move sandbox money.

Every external dependency degrades gracefully: with no PayPal keys the money
endpoints return a clearly labelled mock, and with no OpenAI key the AI
endpoints return an honest, non-AI computed fallback. Nothing is ever faked as
real.
"""

import os
import json
from datetime import date as _date

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

import db

load_dotenv()

app = Flask(__name__)
CORS(
    app,
    origins="*",
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    methods=["GET", "POST", "OPTIONS"],
    supports_credentials=False,
)

db.init_db()


def _today():
    return _date.today().isoformat()

# --------------------------------------------------------------------------- config
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Safety ceiling for an agent-initiated payment (USD). The agent can never move
# more than this, and never anything without explicit user confirmation.
MAX_AGENT_PAYMENT_USD = float(os.getenv("MAX_AGENT_PAYMENT_USD", "500"))


def paypal_available():
    return bool(PAYPAL_CLIENT_ID and PAYPAL_SECRET)


def ai_available():
    return bool(OPENAI_API_KEY)


_openai_client = None


def get_openai_client():
    """Lazily build the OpenAI client. Returns None when no key is set."""
    global _openai_client
    if not OPENAI_API_KEY:
        return None
    if _openai_client is None:
        try:
            from openai import OpenAI

            _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"OpenAI init error: {exc}", flush=True)
            return None
    return _openai_client


# --------------------------------------------------------------------------- PayPal
def get_paypal_token():
    if not paypal_available():
        return None
    try:
        resp = requests.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except Exception as exc:
        print(f"PayPal token error: {exc}", flush=True)
        return None


def _mock_order_id():
    return f"MOCK-ORDER-{os.urandom(4).hex().upper()}"


def approve_url(order):
    """Pull the payer approval link out of a PayPal order response."""
    for link in order.get("links", []):
        if link.get("rel") == "approve":
            return link.get("href")
    return None


def captured_amount(capture_result):
    """The amount actually captured, read from the verified PayPal response.
    Returns None when the response has no capture detail (for example mock mode)."""
    try:
        cap = capture_result["purchase_units"][0]["payments"]["captures"][0]
        return float(cap["amount"]["value"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def paypal_create_order(amount, description=None):
    """Create a sandbox order. Returns (order_dict, mode) with mode live|mock."""
    token = get_paypal_token()
    if not token:
        return (
            {"id": _mock_order_id(), "status": "CREATED", "amount": f"{float(amount):.2f}"},
            "mock",
        )
    unit = {"amount": {"currency_code": "USD", "value": f"{float(amount):.2f}"}}
    if description:
        unit["description"] = str(description)[:127]
    resp = requests.post(
        f"{PAYPAL_BASE}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"intent": "CAPTURE", "purchase_units": [unit]},
        timeout=15,
    )
    resp.raise_for_status()
    return (resp.json(), "live")


def paypal_capture_order(order_id):
    """Capture an approved sandbox order. Returns (result_dict, mode)."""
    if str(order_id).startswith("MOCK"):
        return ({"id": order_id, "status": "COMPLETED"}, "mock")
    token = get_paypal_token()
    if not token:
        return ({"id": order_id, "status": "COMPLETED"}, "mock")
    resp = requests.post(
        f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    return (resp.json(), "live")


def paypal_send_payout(amount, recipient, note=None):
    """Disburse money to a recipient via the Payouts API (server-side, no payer
    approval step). This is what powers an agent-initiated 'send money'.
    Returns (result_dict, mode)."""
    token = get_paypal_token()
    if not token:
        return (
            {
                "batch_id": f"MOCK-PAYOUT-{os.urandom(4).hex().upper()}",
                "status": "SUCCESS",
                "amount": f"{float(amount):.2f}",
                "recipient": recipient,
            },
            "mock",
        )
    sender_batch_id = os.urandom(8).hex()
    payload = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": "You have a payment from PesaAI",
            "email_message": note or "Payment sent via PesaAI",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": f"{float(amount):.2f}", "currency": "USD"},
                "receiver": recipient,
                "note": note or "Payment sent via PesaAI",
                "sender_item_id": sender_batch_id + "-1",
            }
        ],
    }
    resp = requests.post(
        f"{PAYPAL_BASE}/v1/payments/payouts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    batch = data.get("batch_header", {})
    return (
        {
            "batch_id": batch.get("payout_batch_id"),
            "status": batch.get("batch_status", "PENDING"),
            "amount": f"{float(amount):.2f}",
            "recipient": recipient,
            "raw": data,
        },
        "live",
    )


# --------------------------------------------------------------------------- AI
COACH_SYSTEM = (
    "You are PesaAI, a friendly, practical money coach for Kenyan freelancers "
    "and gig workers who earn in USD through PayPal and spend locally. Give "
    "short, concrete, non-judgemental advice about saving, fees, and cash flow. "
    "Amounts are in US dollars unless stated otherwise. Keep replies under 120 "
    "words. If the user writes in Swahili or Sheng, reply in the same language."
)


def _spend_summary(transactions):
    """Deterministic, honest fallback math used when OpenAI is unavailable."""
    spent = sum(abs(t.get("amount", 0)) for t in transactions if t.get("amount", 0) < 0)
    income = sum(t.get("amount", 0) for t in transactions if t.get("amount", 0) > 0)
    return spent, income


def ai_insights(transactions, lang="en"):
    """Return (text, used_ai). Falls back to computed summary without a key."""
    client = get_openai_client()
    spent, income = _spend_summary(transactions)
    if client is None:
        net = income - spent
        return (
            f"You earned ${income:.2f} and spent ${spent:.2f} this period, "
            f"a net of ${net:.2f}. (Connect an OpenAI key to get tailored AI "
            f"insights instead of this summary.)",
            False,
        )
    lang_hint = "Reply in Swahili." if lang == "sw" else "Reply in English."
    prompt = (
        f"{lang_hint} Here are recent transactions as JSON: "
        f"{json.dumps(transactions)}. Give two specific, actionable savings "
        f"insights for this person. Mention fees if relevant."
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": COACH_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=220,
            timeout=30,
        )
        return (resp.choices[0].message.content.strip(), True)
    except Exception as exc:
        print(f"OpenAI insights error: {exc}", flush=True)
        net = income - spent
        return (
            f"You earned ${income:.2f} and spent ${spent:.2f} this period "
            f"(net ${net:.2f}). The AI service is busy right now, please retry.",
            False,
        )


def ai_chat(message, lang="en", history=None):
    """Return (reply, used_ai)."""
    client = get_openai_client()
    if client is None:
        return (
            "I can give richer answers once an OpenAI key is connected. For now: "
            "batch small top-ups into one weekly transfer to cut per-transaction "
            "fees, and keep a small USD buffer in PayPal for lumpy freelance income.",
            False,
        )
    messages = [{"role": "system", "content": COACH_SYSTEM}]
    for turn in (history or [])[-6:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL, messages=messages, max_tokens=240, timeout=30
        )
        return (resp.choices[0].message.content.strip(), True)
    except Exception as exc:
        print(f"OpenAI chat error: {exc}", flush=True)
        return ("The AI coach is busy right now, please try again in a moment.", False)


PROPOSE_PAYMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_payment",
        "description": (
            "Propose sending a PayPal payment to someone. Call this only when the "
            "user clearly wants to send or pay money. Do not send anything, just "
            "propose it for the user to confirm."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount in USD"},
                "recipient": {
                    "type": "string",
                    "description": "Recipient name or email as stated by the user",
                },
                "reason": {
                    "type": "string",
                    "description": "Short reason or memo for the payment",
                },
            },
            "required": ["amount", "recipient"],
        },
    },
}


def ai_agent(message, lang="en", transactions=None):
    """The agentic brain. Returns a dict describing what to do next:

    {"type": "message", "reply": ...}                      normal coaching reply
    {"type": "proposal", "reply": ..., "action": {...}}    a payment to confirm

    This function never moves money. It only decides and proposes.
    """
    client = get_openai_client()
    if client is None:
        return {
            "type": "message",
            "reply": (
                "Connect an OpenAI key to enable the payment agent. Then you can "
                "say things like 'send $15 to jane@example.com for the logo'."
            ),
            "used_ai": False,
        }

    context = ""
    if transactions:
        context = f" Recent transactions for context: {json.dumps(transactions)}."
    lang_hint = "Reply in Swahili." if lang == "sw" else "Reply in English."
    system = (
        COACH_SYSTEM
        + " You can also initiate PayPal payments. When the user asks to send or "
        "pay money, call the propose_payment tool with your best reading of the "
        "amount, recipient, and reason. Never invent a payment the user did not "
        "ask for."
    )
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"{lang_hint} {message}.{context}"},
            ],
            tools=[PROPOSE_PAYMENT_TOOL],
            tool_choice="auto",
            max_tokens=240,
            timeout=30,
        )
        choice = resp.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if tool_calls:
            args = json.loads(tool_calls[0].function.arguments or "{}")
            amount = float(args.get("amount", 0) or 0)
            recipient = (args.get("recipient") or "").strip()
            reason = (args.get("reason") or "").strip()
            reply = (
                f"I can send ${amount:.2f} to {recipient}"
                + (f" for {reason}" if reason else "")
                + ". Confirm below and I'll complete it via PayPal."
            )
            return {
                "type": "proposal",
                "reply": reply,
                "action": {"amount": amount, "recipient": recipient, "reason": reason},
                "used_ai": True,
            }
        return {"type": "message", "reply": (choice.content or "").strip(), "used_ai": True}
    except Exception as exc:
        print(f"OpenAI agent error: {exc}", flush=True)
        return {
            "type": "message",
            "reply": "The AI agent is busy right now, please try again in a moment.",
            "used_ai": False,
        }


SAVINGS_RECIPIENT = os.getenv("SAVINGS_RECIPIENT", "savings@pesaai.app")


def _nudge_finding(transactions):
    """Deterministic pattern detection over the ledger. Returns a base message
    and an optional proposed action, computed from real numbers."""
    topups = [t for t in transactions if t.get("type") == "Top-up" and t.get("amount", 0) > 0]
    small = [t for t in topups if 0 < t.get("amount", 0) <= 20]
    income = sum(t["amount"] for t in transactions if t.get("amount", 0) > 0)
    spent = sum(-t["amount"] for t in transactions if t.get("amount", 0) < 0)
    net = round(income - spent, 2)

    if len(small) >= 3:
        est_fee = round(len(small) * 0.5, 2)
        return {
            "base": (
                f"You made {len(small)} small top-ups, roughly ${est_fee} in avoidable fees. "
                f"Consolidating into one weekly transfer would save that."
            ),
            "action": None,
        }
    if net >= 40:
        save = round(net * 0.2, 2)
        return {
            "base": (
                f"Your income is well above spending (net ${net}). Moving ${save} to savings now "
                f"locks in progress before it gets spent."
            ),
            "action": {"amount": save, "recipient": SAVINGS_RECIPIENT, "reason": "weekly savings"},
        }
    return {
        "base": f"Your spending looks balanced (net ${net}). Keep a small USD buffer for lumpy income.",
        "action": None,
    }


def ai_nudge(transactions, lang="en"):
    """Proactive coaching: find a pattern, phrase it (GPT if available), and
    optionally attach a confirm-gated savings proposal."""
    finding = _nudge_finding(transactions)
    base, action = finding["base"], finding["action"]
    reply, used_ai = base, False
    client = get_openai_client()
    if client is not None:
        lang_hint = "Reply in Swahili." if lang == "sw" else "Reply in English."
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": COACH_SYSTEM},
                    {
                        "role": "user",
                        "content": f"{lang_hint} Rephrase this money tip warmly in under 40 words, keep the numbers exact: {base}",
                    },
                ],
                max_tokens=120,
                timeout=30,
            )
            reply = resp.choices[0].message.content.strip()
            used_ai = True
        except Exception as exc:
            print(f"OpenAI nudge error: {exc}", flush=True)
    out = {"type": "proposal" if action else "message", "reply": reply, "used_ai": used_ai}
    if action:
        out["action"] = action
    return out


# --------------------------------------------------------------------------- routes
@app.route('/')
def home():
    return jsonify({"name": "PesaAI Backend", "status": "running", "live": True}), 200

@app.route('/favicon.ico')
def favicon():
    return "", 204

@app.route('/api/transactions')
def transactions_route():
    try:
        return jsonify({"transactions": db.list_transactions(), "summary": db.summary()})
    except Exception as e:
        return jsonify({"transactions": [], "summary": {}, "error": str(e), "note": "DB init in /tmp/data"}), 200

@app.route('/health')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "paypal": "mock", "ai": "mock"}), 200


@app.route("/api/paypal/create-order", methods=["POST", "OPTIONS"])
def create_order_route():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    amount = data.get("amount", "10.00")
    description = data.get("description")
    try:
        order, mode = paypal_create_order(amount, description)
    except Exception as exc:
        return jsonify({"error": "paypal_create_failed", "detail": str(exc)}), 502
    # Remember the order's amount so capture does not trust a client-sent amount.
    try:
        db.create_order_record(order["id"], float(amount), description)
    except (TypeError, ValueError, KeyError):
        pass
    return jsonify({**order, "mode": mode, "approve_url": approve_url(order)})


@app.route("/api/paypal/capture/<order_id>", methods=["POST", "OPTIONS"])
def capture_order_route(order_id):
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        result, mode = paypal_capture_order(order_id)
    except Exception as exc:
        return jsonify({"error": "paypal_capture_failed", "detail": str(exc)}), 502

    # Record a completed top-up using a TRUSTED amount only: the verified capture
    # response when available, otherwise the amount we stored when the order was
    # created. The client's request body is never trusted for the ledger amount.
    # mark_order_captured() ensures a replayed capture records the row only once.
    recorded = None
    if result.get("status") == "COMPLETED":
        order_rec = db.get_order(order_id)
        amount = captured_amount(result)
        if amount is None and order_rec:
            amount = order_rec["amount"]
        if amount and amount > 0 and db.mark_order_captured(order_id):
            description = (order_rec or {}).get("description") or "PayPal top-up"
            db.add_transaction(_today(), description, amount, "Top-up", "PayPal", sim=False)
            recorded = amount
    return jsonify({**result, "mode": mode, "recorded_amount": recorded})


@app.route("/api/paypal/execute", methods=["POST", "OPTIONS"])
def execute_payment_route():
    """Execute an agent-proposed payment. Called ONLY after the user confirms
    in the UI. Enforces the safety ceiling and sends a real sandbox payout."""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}

    # Idempotency: a repeated confirm (double click, retry) returns the first
    # result instead of sending again.
    idem_key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    cached = db.idempotency_get(idem_key)
    if cached is not None:
        return jsonify({**cached, "idempotent_replay": True})

    try:
        amount = float(data.get("amount", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_amount"}), 400
    recipient = (data.get("recipient") or "").strip()
    reason = (data.get("reason") or "").strip()

    if amount <= 0:
        return jsonify({"error": "amount_must_be_positive"}), 400
    if amount > MAX_AGENT_PAYMENT_USD:
        return (
            jsonify(
                {
                    "error": "amount_over_limit",
                    "limit": MAX_AGENT_PAYMENT_USD,
                    "detail": f"Agent payments are capped at ${MAX_AGENT_PAYMENT_USD:.0f}.",
                }
            ),
            400,
        )
    if not recipient:
        return jsonify({"error": "recipient_required"}), 400

    try:
        result, mode = paypal_send_payout(amount, recipient, reason)
    except Exception as exc:
        return jsonify({"error": "paypal_payout_failed", "detail": str(exc)}), 502

    label = f"Sent to {recipient}" + (f" ({reason})" if reason else "")
    db.add_transaction(_today(), label, -abs(amount), "Payout", "PayPal", sim=False)
    resp = {**result, "mode": mode, "reason": reason}
    db.idempotency_put(idem_key, resp)
    return jsonify(resp)


@app.route("/api/ai/insights", methods=["POST", "OPTIONS"])
def insights_route():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    transactions = data.get("transactions")
    if transactions is None:
        transactions = db.list_transactions()
    lang = data.get("lang", "en")
    text, used_ai = ai_insights(transactions, lang)
    return jsonify(
        {"insights": text, "used_ai": used_ai, "transactions_analyzed": len(transactions)}
    )


@app.route("/api/ai/chat", methods=["POST", "OPTIONS"])
def chat_route():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    lang = data.get("lang", "en")
    history = data.get("history", [])
    if not message:
        return jsonify({"error": "message_required"}), 400
    reply, used_ai = ai_chat(message, lang, history)
    return jsonify({"reply": reply, "used_ai": used_ai})


@app.route("/api/ai/agent", methods=["POST", "OPTIONS"])
def agent_route():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    lang = data.get("lang", "en")
    transactions = data.get("transactions")
    if transactions is None:
        transactions = db.list_transactions()
    if not message:
        return jsonify({"error": "message_required"}), 400
    return jsonify(ai_agent(message, lang, transactions))


@app.route("/api/ai/nudge", methods=["POST", "OPTIONS"])
def nudge_route():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(silent=True) or {}
    lang = data.get("lang", "en")
    transactions = data.get("transactions")
    if transactions is None:
        transactions = db.list_transactions()
    return jsonify(ai_nudge(transactions, lang))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(
        f"Starting PesaAI backend on :{port} "
        f"(paypal={'live' if paypal_available() else 'mock'}, "
        f"ai={'live' if ai_available() else 'mock'})",
        flush=True,
    )
    app.run(host="0.0.0.0", port=port, debug=False)
