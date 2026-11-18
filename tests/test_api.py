import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
from app.core.security import hash_password, create_access_token


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_api.db"
    monkeypatch.setattr("app.config.settings.DATABASE_PATH", test_db)
    init_db(test_db)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_headers():
    token = create_access_token({"sub": "test_admin", "role": "superadmin", "id": 1})
    with get_db() as conn:
        conn.execute("""
            INSERT INTO panel_users (id, username, password_hash, full_name, role, is_active, created_at)
            VALUES (1, 'test_admin', ?, 'Test Admin', 'superadmin', 1, '2026-11-18 12:00:00')
        """, (hash_password("AdminPass123!"),))
    return {"Authorization": f"Bearer {token}"}


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_initial_setup_and_login(client):
    # Check setup status: should be needed since no users exist
    res = client.get("/api/auth/setup-status")
    assert res.status_code == 200
    assert res.json()["setup_needed"] is True

    # Run initial setup
    setup_res = client.post("/api/auth/initial-setup", json={
        "username": "superadmin",
        "password": "SuperSecretPassword123!",
        "full_name": "Main Superadmin"
    })
    assert setup_res.status_code == 200

    # Try running setup again: should be forbidden
    setup_again = client.post("/api/auth/initial-setup", json={
        "username": "intruder",
        "password": "IntruderPassword123!"
    })
    assert setup_again.status_code == 400

    # Login with created admin
    login_res = client.post("/api/auth/login", json={
        "username": "superadmin",
        "password": "SuperSecretPassword123!"
    })
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()


def test_dashboard_and_sessions(client, admin_headers):
    # Insert a test session
    with get_db() as conn:
        conn.execute("""
            INSERT INTO vpn_sessions (
                session_id, virtual_hub, username, client_ip, login_time,
                logout_time, duration_seconds, status, created_at, updated_at
            ) VALUES (
                'SID-ALICE-1', 'DEFAULT', 'synth_alice', '198.51.100.10',
                '2026-11-15 08:00:00', '2026-11-15 09:00:00', 3600,
                'COMPLETED', '2026-11-15 08:00:00', '2026-11-15 09:00:00'
            )
        """)

    # Dashboard summary
    d_res = client.get("/api/dashboard/summary", headers=admin_headers)
    assert d_res.status_code == 200
    data = d_res.json()
    assert data["total_vpn_users"] == 1
    assert data["completed_sessions"] == 1
    assert data["total_duration_seconds"] == 3600

    # Search sessions
    s_res = client.get("/api/sessions?username=synth_alice", headers=admin_headers)
    assert s_res.status_code == 200
    s_data = s_res.json()
    assert s_data["total_count"] == 1
    assert s_data["items"][0]["username"] == "synth_alice"
    assert s_data["summary"]["total_sessions"] == 1

    # Excel export endpoint
    ex_res = client.get("/api/export/excel", headers=admin_headers)
    assert ex_res.status_code == 200
    assert ex_res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # CSV export endpoint
    csv_res = client.get("/api/export/csv", headers=admin_headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
