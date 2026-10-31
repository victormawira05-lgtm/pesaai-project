"""Tests for the PesaAI backend.

External services (PayPal, OpenAI) are mocked so the suite is deterministic and
runs offline. The database is pointed at a temp file and reset before each test.
Both the graceful-fallback paths (no keys) and the live code paths (keys
present, network mocked) are covered.
"""

import os
import json
import tempfile
from types import SimpleNamespace

# Point the DB at a temp file BEFORE importing the app (db reads the path on import).
os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "pesaai_test.db")

import pytest

import db
import app as appmod


@pytest.fixture(autouse=True)
def fresh_db():
    db.reset()
    yield


@pytest.fixture
def client():
    appmod.app.config.update(TESTING=True)
    return appmod.app.test_client()


@pytest.fixture
def no_keys(monkeypatch):
    """Force fallback mode: no PayPal, no OpenAI."""
    monkeypatch.setattr(appmod, "PAYPAL_CLIENT_ID", None)
    monkeypatch.setattr(appmod, "PAYPAL_SECRET", None)
    monkeypatch.setattr(appmod, "OPENAI_API_KEY", None)
    monkeypatch.setattr(appmod, "_openai_client", None)


# --------------------------------------------------------------- fake externals
class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def make_fake_post():
    def fake_post(url, **kwargs):
        if "oauth2/token" in url:
            return FakeResp({"access_token": "FAKE-TOKEN"})
        if "checkout/orders" in url and url.endswith("/capture"):
            return FakeResp(
                {
                    "id": "ORDER123",
                    "status": "COMPLETED",
                    "purchase_units": [{"payments": {"captures": [{"amount": {"value": "12.00", "currency_code": "USD"}}]}}],
                }
            )
        if "checkout/orders" in url:
            return FakeResp(
                {
                    "id": "ORDER123",
                    "status": "CREATED",
                    "links": [
                        {"rel": "approve", "href": "https://sandbox.paypal.com/checkoutnow?token=ORDER123"},
                    ],
                }
            )
        if "payments/payouts" in url:
            return FakeResp({"batch_header": {"payout_batch_id": "PAYOUT9", "batch_status": "PENDING"}})
        raise AssertionError(f"unexpected url {url}")

    return fake_post


def fake_openai_client(content="AI says: save weekly.", tool_args=None):
    message = SimpleNamespace(content=content, tool_calls=None)
    if tool_args is not None:
        message.tool_calls = [SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(tool_args)))]
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: completion)))


# --------------------------------------------------------------- health / home / data
def test_health_reports_mock_without_keys(client, no_keys):
    data = client.get("/health").get_json()
    assert data["status"] == "ok"
    assert data["paypal"] == "mock"
    assert data["ai"] == "mock"


def test_home_lists_endpoints(client):
    data = client.get("/").get_json()
    assert "/api/ai/agent" in data["endpoints"]
    assert "/api/ai/nudge" in data["endpoints"]


def test_transactions_seeded(client):
    data = client.get("/api/transactions").get_json()
    assert len(data["transactions"]) == 5
    assert data["summary"] == {"income": 200.0, "spent": 39.7, "net": 160.3}


# --------------------------------------------------------------- PayPal
def test_create_order_mock_without_keys(client, no_keys):
    data = client.post("/api/paypal/create-order", json={"amount": "25.00"}).get_json()
    assert data["mode"] == "mock"
    assert data["id"].startswith("MOCK-ORDER-")


def test_create_order_live_path(client, monkeypatch):
    monkeypatch.setattr(appmod, "PAYPAL_CLIENT_ID", "id")
    monkeypatch.setattr(appmod, "PAYPAL_SECRET", "secret")
    monkeypatch.setattr(appmod.requests, "post", make_fake_post())
    data = client.post("/api/paypal/create-order", json={"amount": "12.00"}).get_json()
    assert data["mode"] == "live"
    assert "checkoutnow" in data["approve_url"]


def test_capture_records_topup_from_created_order(client, no_keys):
    created = client.post("/api/paypal/create-order", json={"amount": "10.00"}).get_json()
    before = len(client.get("/api/transactions").get_json()["transactions"])
    client.post(f"/api/paypal/capture/{created['id']}", json={})
    data = client.get("/api/transactions").get_json()
    assert len(data["transactions"]) == before + 1
    assert data["summary"]["income"] == 210.0


def test_capture_ignores_client_supplied_amount(client, no_keys):
    # Security: an attacker cannot inflate the ledger via the capture body.
    created = client.post("/api/paypal/create-order", json={"amount": "10.00"}).get_json()
    client.post(f"/api/paypal/capture/{created['id']}", json={"amount": 99999})
    data = client.get("/api/transactions").get_json()
    assert data["summary"]["income"] == 210.0  # rose by 10, not 99999
    assert all(t["amount"] != 99999 for t in data["transactions"])


def test_capture_is_idempotent(client, no_keys):
    created = client.post("/api/paypal/create-order", json={"amount": "10.00"}).get_json()
    oid = created["id"]
    client.post(f"/api/paypal/capture/{oid}", json={})
    client.post(f"/api/paypal/capture/{oid}", json={})  # replayed capture
    topups = [t for t in client.get("/api/transactions").get_json()["transactions"] if t["type"] == "Top-up"]
    assert len(topups) == 2  # one seed top-up + one captured, not three


def test_capture_live_uses_verified_amount(client, monkeypatch):
    monkeypatch.setattr(appmod, "PAYPAL_CLIENT_ID", "id")
    monkeypatch.setattr(appmod, "PAYPAL_SECRET", "secret")
    monkeypatch.setattr(appmod.requests, "post", make_fake_post())
    client.post("/api/paypal/create-order", json={"amount": "12.00"})  # stores ORDER123 at 12.00
    cap = client.post("/api/paypal/capture/ORDER123", json={"amount": 5}).get_json()
    assert cap["recorded_amount"] == 12.00  # from the verified capture response, not the client's 5


# --------------------------------------------------------------- execute + idempotency
def test_execute_rejects_over_limit(client, no_keys):
    resp = client.post("/api/paypal/execute", json={"amount": 10_000, "recipient": "a@b.com"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "amount_over_limit"


def test_execute_rejects_missing_recipient(client, no_keys):
    assert client.post("/api/paypal/execute", json={"amount": 10}).status_code == 400


def test_execute_rejects_non_positive(client, no_keys):
    assert client.post("/api/paypal/execute", json={"amount": 0, "recipient": "a@b.com"}).status_code == 400


def test_execute_mock_payout_records_txn(client, no_keys):
    data = client.post("/api/paypal/execute", json={"amount": 15, "recipient": "jane@example.com", "reason": "logo"}).get_json()
    assert data["mode"] == "mock"
    txns = client.get("/api/transactions").get_json()["transactions"]
    assert any(t["type"] == "Payout" and t["amount"] == -15.0 for t in txns)


def test_execute_idempotent_no_double_send(client, no_keys):
    body = {"amount": 20, "recipient": "x@y.com", "idempotency_key": "key-1"}
    r1 = client.post("/api/paypal/execute", json=body).get_json()
    r2 = client.post("/api/paypal/execute", json=body).get_json()
    assert r2.get("idempotent_replay") is True
    assert r1["batch_id"] == r2["batch_id"]
    payouts = [t for t in client.get("/api/transactions").get_json()["transactions"] if t["type"] == "Payout"]
    assert len(payouts) == 1  # only one payment recorded despite two calls


def test_execute_live_payout(client, monkeypatch):
    monkeypatch.setattr(appmod, "PAYPAL_CLIENT_ID", "id")
    monkeypatch.setattr(appmod, "PAYPAL_SECRET", "secret")
    monkeypatch.setattr(appmod.requests, "post", make_fake_post())
    data = client.post("/api/paypal/execute", json={"amount": 20, "recipient": "x@y.com"}).get_json()
    assert data["mode"] == "live"
    assert data["batch_id"] == "PAYOUT9"


# --------------------------------------------------------------- AI insights / chat
def test_insights_fallback_without_key(client, no_keys):
    data = client.post("/api/ai/insights", json={"transactions": [{"amount": -20}, {"amount": 150}]}).get_json()
    assert data["used_ai"] is False
    assert "150.00" in data["insights"] and "20.00" in data["insights"]


def test_insights_defaults_to_db(client, no_keys):
    data = client.post("/api/ai/insights", json={}).get_json()
    assert data["transactions_analyzed"] == 5  # pulled from the seeded ledger


def test_insights_live_path(client, monkeypatch):
    monkeypatch.setattr(appmod, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(appmod, "get_openai_client", lambda: fake_openai_client("Two tips: ..."))
    data = client.post("/api/ai/insights", json={"transactions": [{"amount": 10}]}).get_json()
    assert data["used_ai"] is True and data["insights"] == "Two tips: ..."


def test_chat_requires_message(client, no_keys):
    assert client.post("/api/ai/chat", json={"message": ""}).status_code == 400


def test_chat_live_path(client, monkeypatch):
    monkeypatch.setattr(appmod, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(appmod, "get_openai_client", lambda: fake_openai_client("Hujambo! Save weekly."))
    data = client.post("/api/ai/chat", json={"message": "how do I save?", "lang": "sw"}).get_json()
    assert data["used_ai"] is True and "Save weekly" in data["reply"]


# --------------------------------------------------------------- AI agent
def test_agent_fallback_without_key(client, no_keys):
    data = client.post("/api/ai/agent", json={"message": "hi"}).get_json()
    assert data["type"] == "message" and data["used_ai"] is False


def test_agent_proposes_payment(client, monkeypatch):
    monkeypatch.setattr(appmod, "OPENAI_API_KEY", "sk-x")
    monkeypatch.setattr(
        appmod, "get_openai_client",
        lambda: fake_openai_client(tool_args={"amount": 15, "recipient": "jane@example.com", "reason": "logo"}),
    )
    data = client.post("/api/ai/agent", json={"message": "send $15 to jane for the logo"}).get_json()
    assert data["type"] == "proposal"
    assert data["action"] == {"amount": 15, "recipient": "jane@example.com", "reason": "logo"}


# --------------------------------------------------------------- proactive nudge
def test_nudge_proposes_savings_on_high_net(client, no_keys):
    # Seeded net is 160.3 (>= 40), so the nudge proposes moving 20% to savings.
    data = client.post("/api/ai/nudge", json={}).get_json()
    assert data["type"] == "proposal"
    assert data["used_ai"] is False
    assert data["action"]["recipient"] == appmod.SAVINGS_RECIPIENT
    assert data["action"]["amount"] == round(160.3 * 0.2, 2)
