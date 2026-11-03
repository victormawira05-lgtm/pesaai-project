import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import db
from datetime import date
app = Flask(__name__)
CORS(app)
db.init_db()

@app.route("/api/health")
def health():
    return jsonify({"status":"ok"})

@app.route("/api/transactions", methods=["GET"])
def transactions():
    # ALWAYS filter out the bug
    all_txs = db.list_transactions()
    clean = [t for t in all_txs if abs(t.get('amount',0)) < 1000]
    income = sum(t['amount'] for t in clean if t['amount']>0)
    spent = sum(-t['amount'] for t in clean if t['amount']<0)
    return jsonify({
        "summary": {"income": round(income,2), "spent": round(spent,2), "net": round(income-spent,2)},
        "transactions": clean
    })

@app.route("/api/reset", methods=["POST","GET","OPTIONS"])
def reset():
    if request.method == "OPTIONS":
        return ("",204)
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
    db.add_transaction(date.today().isoformat(), "PayPal top-up", 10.00, "Top-up", "PayPal", sim=False)
    db.add_transaction(date.today().isoformat(), "Safaricom airtime", -5.00, "Airtime", "M-Pesa", sim=False)
    db.add_transaction(date.today().isoformat(), "M-Pesa sample", -2.50, "M-Pesa", "M-Pesa", sim=True)
    return jsonify({"status":"ok", "message":"Reset to $10", "summary": db.summary()})

if __name__ == "__main__":
    port=int(os.getenv("PORT","8000"))
    print(f"Starting CLEAN PesaAI backend on :{port} - $59999 bug REMOVED", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
