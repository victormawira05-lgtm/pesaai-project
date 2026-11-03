import os, sqlite3, json
from datetime import date

DB_PATH = os.getenv("DB_PATH", "/tmp/data/pesa.db")

def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

get_connection = _get_conn

def init_db():
    conn = _get_conn()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        description TEXT,
        amount REAL,
        type TEXT,
        source TEXT,
        is_sim INTEGER DEFAULT 0
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        amount REAL,
        description TEXT,
        captured INTEGER DEFAULT 0
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS idempotency (
        key TEXT PRIMARY KEY,
        response TEXT
    )""")
    conn.commit()
    conn.close()

def list_transactions():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM transactions ORDER BY date DESC, id DESC").fetchall()
    conn.close()
    out=[]
    for r in rows:
        out.append({
            "id": r["id"],
            "date": r["date"],
            "desc": r["description"],
            "description": r["description"],
            "amount": r["amount"],
            "type": r["type"],
            "method": r["source"],
            "source": r["source"],
            "sim": bool(r["is_sim"])
        })
    return out

def summary():
    txs = list_transactions()
    income = sum(t["amount"] for t in txs if t["amount"]>0)
    spent = sum(-t["amount"] for t in txs if t["amount"]<0)
    return {"income": round(income,2), "spent": round(spent,2), "net": round(income-spent,2)}

MAX_TOPUP = 500.0
def add_transaction(date_str, desc, amount, type_, source, sim=False):
    amt = float(amount)
    # BLOCK the $59999 bug
    if amt > MAX_TOPUP:
        print(f"⛔ BLOCKED huge top-up ${amt} - {desc} - capping to $10")
        amt = 10.0
        amount = 10.0
    # also block huge payouts from that bug
    if amt < -MAX_TOPUP:
        print(f"⛔ BLOCKED huge payout ${amt} - rejecting")
        return

    conn = _get_conn()
    conn.execute("INSERT INTO transactions (date, description, amount, type, source, is_sim) VALUES (?,?,?,?,?,?)",
                 (date_str, desc, float(amount), type_, source, 1 if sim else 0))
    conn.commit()
    conn.close()

def reset_to_demo():
    conn = _get_conn()
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM idempotency")
    conn.commit()
    conn.close()
    init_db()
    add_transaction("2026-10-20", "PayPal top-up", 10.00, "Top-up", "PayPal", sim=False)
    add_transaction("2026-10-20", "Safaricom airtime", -5.00, "Airtime", "M-Pesa", sim=False)
    add_transaction("2026-10-20", "M-Pesa sample", -2.50, "M-Pesa", "M-Pesa", sim=True)
    return list_transactions()

# --- functions used by app.py ---
def create_order_record(order_id, amount, desc):
    conn=_get_conn()
    conn.execute("INSERT OR REPLACE INTO orders (id, amount, description) VALUES (?,?,?)", (order_id, float(amount), desc))
    conn.commit()
    conn.close()

def get_order(order_id):
    conn=_get_conn()
    row=conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if not row: return None
    return {"id": row["id"], "amount": row["amount"], "description": row["description"], "captured": row["captured"]}

def mark_order_captured(order_id):
    conn=_get_conn()
    row=conn.execute("SELECT captured FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row or row["captured"]==1:
        conn.close()
        return False
    conn.execute("UPDATE orders SET captured=1 WHERE id=?", (order_id,))
    conn.commit()
    conn.close()
    return True

def idempotency_get(key):
    if not key: return None
    conn=_get_conn()
    row=conn.execute("SELECT response FROM idempotency WHERE key=?", (key,)).fetchone()
    conn.close()
    return json.loads(row["response"]) if row else None

def idempotency_put(key, resp):
    if not key: return
    conn=_get_conn()
    conn.execute("INSERT OR REPLACE INTO idempotency (key, response) VALUES (?,?)", (key, json.dumps(resp)))
    conn.commit()
    conn.close()
