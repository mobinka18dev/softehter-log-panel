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


def test_add_user_and_strict_rbac(client, admin_headers):
    # 1. Superadmin creates a viewer user
    create_viewer_res = client.post("/api/panel-users", headers=admin_headers, json={
        "username": "viewer_user",
        "password": "ViewerPassword123!",
        "full_name": "Report Viewer",
        "role": "viewer"
    })
    assert create_viewer_res.status_code == 200
    assert create_viewer_res.json()["username"] == "viewer_user"

    # 2. Superadmin creates an admin user
    create_admin_res = client.post("/api/panel-users", headers=admin_headers, json={
        "username": "sub_admin",
        "password": "AdminPassword123!",
        "full_name": "Sub Administrator",
        "role": "admin"
    })
    assert create_admin_res.status_code == 200

    # 3. Viewer login and token
    v_login = client.post("/api/auth/login", json={
        "username": "viewer_user",
        "password": "ViewerPassword123!"
    })
    assert v_login.status_code == 200
    viewer_token = v_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # 4. Admin login and token
    a_login = client.post("/api/auth/login", json={
        "username": "sub_admin",
        "password": "AdminPassword123!"
    })
    assert a_login.status_code == 200
    sub_admin_token = a_login.json()["access_token"]
    sub_admin_headers = {"Authorization": f"Bearer {sub_admin_token}"}

    # --- RBAC Enforcement on Viewer ---
    # a) Blocked from viewing Panel Users
    assert client.get("/api/panel-users", headers=viewer_headers).status_code == 403
    # b) Blocked from creating Panel Users
    assert client.post("/api/panel-users", headers=viewer_headers, json={
        "username": "hacker", "password": "Password123!", "role": "viewer"
    }).status_code == 403
    # c) Blocked from Audit Logs
    assert client.get("/api/audit-logs", headers=viewer_headers).status_code == 403
    # d) Blocked from Log Sync Status, Diagnostics, and Trigger
    assert client.get("/api/sync/status", headers=viewer_headers).status_code == 403
    assert client.get("/api/sync/diagnostics", headers=viewer_headers).status_code == 403
    assert client.post("/api/sync/run", headers=viewer_headers).status_code == 403
    # e) Allowed on Dashboard and Sessions
    assert client.get("/api/dashboard/summary", headers=viewer_headers).status_code == 200
    assert client.get("/api/sessions", headers=viewer_headers).status_code == 200

    # --- RBAC Enforcement on Sub Admin ---
    # a) Allowed to view Panel Users
    list_users_res = client.get("/api/panel-users", headers=sub_admin_headers)
    assert list_users_res.status_code == 200
    assert len(list_users_res.json()) >= 3
    # b) Blocked from creating Panel Users (Superadmin only)
    assert client.post("/api/panel-users", headers=sub_admin_headers, json={
        "username": "another_user", "password": "Password123!", "role": "viewer"
    }).status_code == 403
    # c) Allowed on Audit Logs
    assert client.get("/api/audit-logs", headers=sub_admin_headers).status_code == 200
    # d) Allowed on Sync
    assert client.get("/api/sync/status", headers=sub_admin_headers).status_code == 200
    assert client.get("/api/sync/diagnostics", headers=sub_admin_headers).status_code == 200
