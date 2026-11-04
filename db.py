import sqlite3, os
DB_PATH = os.getenv("DB_PATH", "pesaai.db")

def _get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_conn()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        description TEXT,
        amount REAL,
        type TEXT,
        method TEXT,
        sim INTEGER DEFAULT 0
    )""")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        amount REAL,
        status TEXT DEFAULT 'CREATED'
    )""")
    conn.commit()
    conn.close()

def list_transactions():
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM transactions ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_transaction(date, desc, amount, typ, method, sim=False):
    conn = _get_conn()
    conn.execute("INSERT INTO transactions (date, description, amount, type, method, sim) VALUES (?,?,?,?,?,?)",
                 (date, desc, float(amount), typ, method, int(sim)))
    conn.commit()
    conn.close()

def add_order(order_id, amount):
    try:
        conn = _get_conn()
        conn.execute("INSERT OR REPLACE INTO orders (id, amount, status) VALUES (?,?,?)", (order_id, float(amount), "CREATED"))
        conn.commit()
        conn.close()
    except: pass

def summary():
    txs = list_transactions()
    clean = [t for t in txs if abs(t.get('amount',0)) < 1000]
    income = sum(t['amount'] for t in clean if t['amount']>0)
    spent = sum(-t['amount'] for t in clean if t['amount']<0)
    return {"income": round(income,2), "spent": round(spent,2), "net": round(income-spent,2)}