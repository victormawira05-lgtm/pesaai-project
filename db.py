"""SQLite persistence for PesaAI.

Self-contained and zero-config: the database file is created and seeded on first
use, so it "just deploys" with the app, no external database service required.
Uses the stdlib sqlite3 module, so there is no extra dependency.

Note: on hosts with an ephemeral filesystem (for example Render's free tier) the
file persists across requests within a running instance but resets on redeploy.
That is fine for the demo; point DATABASE_PATH at a mounted disk for durable
storage.
"""

import os
import json
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "pesaai.db"))

_LOCK = threading.Lock()

SEED = [
    ("2026-10-19", "Upwork freelance pay", 150.0, "Income", "PayPal", 0),
    ("2026-10-17", "PayPal top-up", 50.0, "Top-up", "PayPal", 0),
    ("2026-10-20", "Safaricom airtime", -5.0, "Airtime", "M-Pesa", 1),
    ("2026-10-18", "Naivas supermarket", -28.5, "Food", "M-Pesa", 1),
    ("2026-10-16", "Bolt ride", -6.2, "Transport", "M-Pesa", 1),
]


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    """Create tables if missing and seed the ledger once."""
    with _LOCK, _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                description TEXT NOT NULL,
                amount      REAL NOT NULL,
                type        TEXT NOT NULL,
                method      TEXT NOT NULL,
                sim         INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency (
                key        TEXT PRIMARY KEY,
                response   TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id    TEXT PRIMARY KEY,
                amount      REAL NOT NULL,
                description TEXT,
                captured    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
        if count == 0:
            conn.executemany(
                "INSERT INTO transactions (date, description, amount, type, method, sim, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(d, desc, amt, typ, meth, sim, _now()) for (d, desc, amt, typ, meth, sim) in SEED],
            )


def reset():
    """Drop and recreate everything, then reseed. Used by tests."""
    with _LOCK, _conn() as conn:
        conn.execute("DROP TABLE IF EXISTS transactions")
        conn.execute("DROP TABLE IF EXISTS idempotency")
        conn.execute("DROP TABLE IF EXISTS orders")
    init_db()


def create_order_record(order_id, amount, description=None):
    """Remember the amount an order was created for, so capture does not have to
    trust a client-supplied amount."""
    with _LOCK, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO orders (order_id, amount, description, captured, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (order_id, float(amount), description or "PayPal top-up", _now()),
        )


def get_order(order_id):
    with _conn() as conn:
        row = conn.execute(
            "SELECT order_id, amount, description, captured FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
    return dict(row) if row else None


def mark_order_captured(order_id):
    """Atomically flip an order to captured. Returns True only on the first
    transition, so a replayed capture cannot record the ledger row twice."""
    with _LOCK, _conn() as conn:
        cur = conn.execute("UPDATE orders SET captured = 1 WHERE order_id = ? AND captured = 0", (order_id,))
        return cur.rowcount == 1


def list_transactions():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, date, description AS desc, amount, type, method, sim "
            "FROM transactions ORDER BY date DESC, id DESC"
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["sim"] = bool(d["sim"])
        out.append(d)
    return out


def add_transaction(date, description, amount, type, method, sim=False):
    with _LOCK, _conn() as conn:
        cur = conn.execute(
            "INSERT INTO transactions (date, description, amount, type, method, sim, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, description, float(amount), type, method, 1 if sim else 0, _now()),
        )
        return cur.lastrowid


def summary():
    txns = list_transactions()
    income = sum(t["amount"] for t in txns if t["amount"] > 0)
    spent = sum(-t["amount"] for t in txns if t["amount"] < 0)
    return {"income": round(income, 2), "spent": round(spent, 2), "net": round(income - spent, 2)}


def idempotency_get(key):
    if not key:
        return None
    with _conn() as conn:
        row = conn.execute("SELECT response FROM idempotency WHERE key = ?", (key,)).fetchone()
    return json.loads(row["response"]) if row else None


def idempotency_put(key, response):
    if not key:
        return
    with _LOCK, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO idempotency (key, response, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(response), _now()),
        )
