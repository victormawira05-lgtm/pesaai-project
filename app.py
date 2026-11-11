from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import uuid, os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, origins="*", methods=["GET","POST","OPTIONS"], allow_headers=["Content-Type"])

def uid(): return str(uuid.uuid4())

def get_initial_tx():
    return [
     {"id": uid(), "date": "2026-11-10", "desc": "Demo reset", "merchant": "System", "amount": 10.00, "type": "Income", "method": "Demo", "sim": False},
     {"id": uid(), "date": "2026-11-09", "desc": "Upwork", "merchant": "Upwork", "amount": 150.00, "type": "Income", "method": "PayPal", "sim": False},
     {"id": uid(), "date": "2026-11-10", "desc": "Naivas", "merchant": "Naivas", "amount": -28.00, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-10", "desc": "Airtime", "merchant": "Safaricom", "amount": -5.00, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-09", "desc": "Airtime", "merchant": "Safaricom", "amount": -5.00, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-09", "desc": "Bolt Ride", "merchant": "Bolt", "amount": -6.70, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-08", "desc": "Airtime", "merchant": "Safaricom", "amount": -5.00, "type": "Expense", "method": "M-Pesa", "sim": True},
    ]

transactions = get_initial_tx()

def calc_summary():
    inc = sum(t["amount"] for t in transactions if t["amount"]>0)
    spent = abs(sum(t["amount"] for t in transactions if t["amount"]<0))
    return {"income": inc, "spent": spent, "net": inc-spent, "balance": inc-spent, "totalIncome": inc, "totalExpenses": spent}

@app.route("/api/transactions")
def get_tx(): return jsonify({"transactions": transactions, "summary": calc_summary()})

@app.route("/api/balance")
def bal(): return jsonify(calc_summary())

@app.route("/api/reset", methods=["POST","GET","OPTIONS"])
@app.route("/api/reset-demo", methods=["POST","GET","OPTIONS"])
def reset():
    global transactions
    transactions = get_initial_tx()
    return jsonify({"message": "Reset to $110.30 demo", "status":"ok", "transactions": transactions, "summary": calc_summary()})

@app.route("/api/paypal/create-order", methods=["POST","GET","OPTIONS"])
@app.route("/api/paypal", methods=["POST","GET","OPTIONS"])
def paypal():
    global transactions
    # get amount from body if sent
    data = request.get_json(silent=True) or {}
    amt = float(data.get("amount", 10))
    new_tx = {"id": uid(), "date": "2026-11-11", "desc": "PayPal top-up", "merchant": "PayPal", "amount": amt, "type": "Income", "method": "PayPal", "sim": False}
    transactions.append(new_tx)
    return jsonify({"message": f"PayPal ${amt} added", "status":"success", "transactions": transactions, "summary": calc_summary()})

@app.route("/api/chat", methods=["POST","OPTIONS"])
def chat():
    if request.method == "OPTIONS": return jsonify({})
    m=(request.get_json(silent=True) or {}).get("message","")
    s=calc_summary()
    return jsonify({"reply": f"You have ${s['income']:.2f} income, spent ${s['spent']:.2f}, net ${s['net']:.2f}. Upwork $150 + Demo $10 = $160. You said: {m}"})

@app.route("/api/health")
@app.route("/health")
def health(): return jsonify({"status":"ok"})

@app.route("/")
def home(): return send_from_directory('.', 'index.html') if os.path.exists("index.html") else jsonify(calc_summary())

@app.route("/<path:p>")
def static_files(p):
    if os.path.exists(p): return send_from_directory('.', p)
    return send_from_directory('.', 'index.html') if os.path.exists("index.html") else jsonify({"error":"not found"})

if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))