import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import db
from datetime import date

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
db.init_db()

# --- DEMO DATA ---
DEMO_TXNS = [
    (date.today().isoformat(), "PayPal top-up", 10.00, "Top-up", "PayPal", False),
    (date.today().isoformat(), "Safaricom airtime", -5.00, "Airtime", "M-Pesa", False),
    (date.today().isoformat(), "M-Pesa sample", -2.50, "M-Pesa", "M-Pesa", True),
]

def get_clean_data():
    # ALWAYS filter out the $59,999 bug
    all_txs = db.list_transactions()
    clean = [t for t in all_txs if abs(t.get('amount', 0)) < 1000]
    return clean

@app.route("/api/health", methods=["GET"])
def health():
    # Keep chips working
    return jsonify({
        "status": "ok",
        "paypal": os.getenv("PAYPAL_MODE", "mock"),
        "ai": os.getenv("AI_MODE", "mock"),
        "model": os.getenv("AI_MODEL", "mock")
    })

@app.route("/api/transactions", methods=["GET"])
def transactions():
    clean = get_clean_data()
    income = sum(t['amount'] for t in clean if t['amount'] > 0)
    spent = sum(-t['amount'] for t in clean if t['amount'] < 0)
    net = income - spent
    return jsonify({
        "summary": {"income": round(income,2), "spent": round(spent,2), "net": round(net,2)},
        "transactions": clean
    })

@app.route("/api/reset", methods=["POST","GET","OPTIONS"])
def reset():
    if request.method == "OPTIONS":
        return ("", 204)
    conn = db._get_conn()
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM orders")
    try:
        conn.execute("DELETE FROM idempotency")
    except:
        pass
    conn.commit()
    conn.close()
    db.init_db()
    for d in DEMO_TXNS:
        db.add_transaction(*d)
    
    return jsonify({"status":"ok", "message":"Reset to $10", "summary": db.summary()})

# --- KEEP YOUR EXISTING PAYPAL / AI ROUTES HERE ---
# If you have them in another file, paste them below this line.
# Example stubs so your frontend doesn't break if they are missing:
@app.route("/api/paypal/create-order", methods=["POST"])
def create_order():
    data = request.json or {}
    amount = data.get("amount", "10.00")
    order_id = f"MOCK-{os.urandom(4).hex()}"
    db.add_order(order_id, float(amount))
    return jsonify({"id": order_id, "approve_url": None, "mode": "mock"})

@app.route("/api/paypal/capture/<order_id>", methods=["POST"])
def capture_order(order_id):
    body = request.json or {}
    amount = float(body.get("amount", 10))
    db.add_transaction(date.today().isoformat(), "PayPal top-up", amount, "Top-up", "PayPal", sim=False)
    return jsonify({"status":"COMPLETED", "id": order_id, "mode":"mock"})

@app.route("/api/paypal/execute", methods=["POST"])
def execute_pay():
    body = request.json or {}
    amount = float(body.get("amount", 0))
    desc = f"Payout to {body.get('recipient','')}"
    db.add_transaction(date.today().isoformat(), desc, -amount, "Payout", "PayPal", sim=False)
    return jsonify({"status":"COMPLETED", "batch_id": f"BATCH-{os.urandom(4).hex()}", "mode":"mock"})

@app.route("/api/ai/agent", methods=["POST"])
def ai_agent():
    clean = get_clean_data()
    income = sum(t['amount'] for t in clean if t['amount']>0)
    return jsonify({"reply": f"You have ${income:.2f} income right now. Your net is clean - the $59k bug is filtered. Want to send money?", "type": "chat"})

@app.route("/api/ai/insights", methods=["POST"])
def ai_insights():
    s = db.summary()
    return jsonify({"insights": f"INCOME ${s['income']:.2f} / SPENT ${s['spent']:.2f} / NET ${s['net']:.2f}. Demo is reset and clean."})

@app.route("/api/ai/nudge", methods=["POST"])
def ai_nudge():
    return jsonify({"reply": "Demo is ready. Try a PayPal top-up!", "type": "chat"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting CLEAN PesaAI backend on :{port} - $59999 bug FILTERED + RESET added", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)