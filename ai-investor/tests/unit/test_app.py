from fastapi.testclient import TestClient

from ai_investor.main import create_app

client = TestClient(create_app())


def test_health_reports_simulation_only():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["simulation_only"] is True
    assert "aucune transaction réelle" in body["disclaimer"]


def test_index_shows_disclaimer_and_security_headers():
    response = client.get("/")
    assert response.status_code == 200
    assert "Simulation uniquement" in response.text
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_no_execution_routes_exposed():
    paths = [route.path.lower() for route in create_app().routes]  # type: ignore[attr-defined]
    for word in ("order", "transfer", "withdraw", "broker", "login-broker", "account"):
        assert not any(word in p for p in paths), (word, paths)


def test_order_endpoint_does_not_exist():
    assert client.post("/orders", json={"isin": "X", "qty": 1}).status_code in (404, 405)
