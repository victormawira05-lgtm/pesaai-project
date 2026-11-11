from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import uuid, os
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app, origins="*")
def uid(): return str(uuid.uuid4())
def get_initial_tx():
    return [
     {"id": uid(), "date": "2026-11-10", "desc": "Upwork Income", "merchant": "Upwork", "amount": 150, "type": "Income", "method": "PayPal", "sim": False},
     {"id": uid(), "date": "2026-11-10", "desc": "Naivas Shopping", "merchant": "Naivas", "amount": -28, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-10", "desc": "Airtime", "merchant": "Safaricom", "amount": -5, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-09", "desc": "Bolt Ride", "merchant": "Bolt", "amount": -6.7, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-09", "desc": "Airtime", "merchant": "Safaricom", "amount": -5, "type": "Expense", "method": "M-Pesa", "sim": True},
     {"id": uid(), "date": "2026-11-08", "desc": "Demo reset", "merchant": "System", "amount": 10, "type": "Income", "method": "Demo", "sim": False},
    ]
transactions = get_initial_tx()
def calc_summary():
    inc = sum(t["amount"] for t in transactions if t["amount"]>0)
    spent = abs(sum(t["amount"] for t in transactions if t["amount"]<0))
    return {"income": inc, "spent": spent, "net": inc-spent, "balance": inc-spent}
@app.route("/api/transactions")
def get_tx(): return jsonify({"transactions": transactions, "summary": calc_summary()})
@app.route("/api/balance")
def bal(): return jsonify(calc_summary())
@app.route("/api/reset", methods=["POST","GET"])
@app.route("/api/reset-demo", methods=["POST","GET"])
def reset():
    global transactions
    transactions = get_initial_tx()
    return jsonify({"message": "Old PesaAI restored!", "status":"ok"})
@app.route("/api/paypal/create-order", methods=["POST","GET"])
@app.route("/api/paypal", methods=["POST","GET"])
def paypal(): return jsonify({"message":"PayPal $10 mock created", "status":"success"})
@app.route("/api/chat", methods=["POST"])
def chat():
    m=(request.get_json(silent=True) or {}).get("message","")
    s=calc_summary()
    return jsonify({"reply": f"Balance ${s['net']:.2f} after Upwork etc. You asked: {m}"})
@app.route("/api/health")
@app.route("/health")
def health(): return jsonify({"status":"ok"})
@app.route("/")
def home(): return send_from_directory('.', 'index.html') if os.path.exists("index.html") else jsonify({"message":"PesaAI Running"})
@app.route("/<path:p>")
def static_files(p):
    if os.path.exists(p): return send_from_directory('.', p)
    return send_from_directory('.', 'index.html')
if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))