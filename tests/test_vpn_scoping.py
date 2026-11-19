import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db, get_db
from app.core.security import hash_password, create_access_token


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_scoping.db"
    monkeypatch.setattr("app.config.settings.DATABASE_PATH", test_db)
    init_db(test_db)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_auto_migration_existing_db_without_allowed_vpn_users(tmp_path):
    """Test that existing databases without allowed_vpn_users column migrate seamlessly."""
    legacy_db_path = tmp_path / "legacy.db"
    
    # 1. Manually create legacy table without allowed_vpn_users
    with sqlite3.connect(str(legacy_db_path)) as conn:
        conn.execute("""
            CREATE TABLE panel_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                role TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                failed_login_attempts INTEGER DEFAULT 0,
                locked_until TEXT
            );
        """)
        conn.execute("""
            INSERT INTO panel_users (username, password_hash, full_name, role, created_at)
            VALUES ('old_admin', 'hash123', 'Old Admin', 'admin', '2026-11-01 10:00:00')
        """)
        conn.commit()

        # Verify column did NOT exist
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(panel_users);")
        cols_before = [c[1] for c in cursor.fetchall()]
        assert "allowed_vpn_users" not in cols_before

    # 2. Run init_db on the legacy DB
    init_db(legacy_db_path)

    # 3. Verify column now exists and old data is preserved
    with sqlite3.connect(str(legacy_db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(panel_users);")
        cols_after = [c["name"] for c in cursor.fetchall()]
        assert "allowed_vpn_users" in cols_after

        cursor.execute("SELECT username, allowed_vpn_users FROM panel_users WHERE username = 'old_admin'")
        row = cursor.fetchone()
        assert row["username"] == "old_admin"
        assert row["allowed_vpn_users"] is None


def test_panel_users_crud_allowed_vpn_users(client):
    """Test creating, listing, and updating allowed_vpn_users via API."""
    superadmin_token = create_access_token({"sub": "super_root", "role": "superadmin", "id": 1})
    with get_db() as conn:
        conn.execute("""
            INSERT INTO panel_users (id, username, password_hash, full_name, role, is_active, created_at)
            VALUES (1, 'super_root', ?, 'Root', 'superadmin', 1, '2026-11-18 12:00:00')
        """, (hash_password("SuperPass123!"),))

    admin_headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Create a user with restricted allowed_vpn_users
    create_res = client.post("/api/panel-users", headers=admin_headers, json={
        "username": "viewer_scoped",
        "password": "ViewerPassword123!",
        "full_name": "Scoped Viewer",
        "role": "viewer",
        "allowed_vpn_users": ["vpn_alice", "vpn_bob"]
    })
    assert create_res.status_code == 200
    user_id = create_res.json()["id"]

    # 2. List users and verify allowed_vpn_users is returned as parsed list
    list_res = client.get("/api/panel-users", headers=admin_headers)
    assert list_res.status_code == 200
    users = list_res.json()
    scoped_user = next(u for u in users if u["id"] == user_id)
    assert scoped_user["allowed_vpn_users"] == ["vpn_alice", "vpn_bob"]

    # 3. Update user: change scope to a single user
    update_res = client.put(f"/api/panel-users/{user_id}", headers=admin_headers, json={
        "allowed_vpn_users": ["vpn_charlie"]
    })
    assert update_res.status_code == 200

    list_res2 = client.get("/api/panel-users", headers=admin_headers)
    scoped_user2 = next(u for u in list_res2.json() if u["id"] == user_id)
    assert scoped_user2["allowed_vpn_users"] == ["vpn_charlie"]

    # 4. Update user: clear scope (make unrestricted)
    update_res_clear = client.put(f"/api/panel-users/{user_id}", headers=admin_headers, json={
        "allowed_vpn_users": None
    })
    assert update_res_clear.status_code == 200

    list_res3 = client.get("/api/panel-users", headers=admin_headers)
    scoped_user3 = next(u for u in list_res3.json() if u["id"] == user_id)
    assert scoped_user3["allowed_vpn_users"] is None


def test_restricted_scoping_enforcement_end_to_end(client):
    """
    Test strict SQL-level scoping enforcement across Dashboard, Sessions, Active Sessions,
    Usernames, and Export endpoints for a restricted user vs unrestricted user.
    """
    # 1. Seed sessions and raw events for 3 different VPN users
    with get_db() as conn:
        # alice: 2 completed, 1 active
        conn.execute("""
            INSERT INTO vpn_sessions (session_id, virtual_hub, username, client_ip, login_time, logout_time, duration_seconds, status, created_at, updated_at)
            VALUES 
            ('SID-ALICE-1', 'DEFAULT', 'alice', '1.1.1.1', '2026-11-18 10:00:00', '2026-11-18 11:00:00', 3600, 'COMPLETED', '2026-11-18 10:00:00', '2026-11-18 11:00:00'),
            ('SID-ALICE-2', 'DEFAULT', 'alice', '1.1.1.1', '2026-11-18 12:00:00', '2026-11-18 13:00:00', 3600, 'COMPLETED', '2026-11-18 12:00:00', '2026-11-18 13:00:00'),
            ('SID-ALICE-3', 'DEFAULT', 'alice', '1.1.1.1', '2026-11-18 14:00:00', NULL, NULL, 'ACTIVE', '2026-11-18 14:00:00', '2026-11-18 14:00:00')
        """)
        # bob: 1 completed
        conn.execute("""
            INSERT INTO vpn_sessions (session_id, virtual_hub, username, client_ip, login_time, logout_time, duration_seconds, status, created_at, updated_at)
            VALUES 
            ('SID-BOB-1', 'HUB_SEC', 'bob', '2.2.2.2', '2026-11-18 11:00:00', '2026-11-18 11:30:00', 1800, 'COMPLETED', '2026-11-18 11:00:00', '2026-11-18 11:30:00')
        """)
        # charlie: 2 completed, 1 active
        conn.execute("""
            INSERT INTO vpn_sessions (session_id, virtual_hub, username, client_ip, login_time, logout_time, duration_seconds, status, created_at, updated_at)
            VALUES 
            ('SID-CHARLIE-1', 'DEFAULT', 'charlie', '3.3.3.3', '2026-11-18 08:00:00', '2026-11-18 09:00:00', 3600, 'COMPLETED', '2026-11-18 08:00:00', '2026-11-18 09:00:00'),
            ('SID-CHARLIE-2', 'DEFAULT', 'charlie', '3.3.3.3', '2026-11-18 09:30:00', '2026-11-18 10:30:00', 3600, 'COMPLETED', '2026-11-18 09:30:00', '2026-11-18 10:30:00'),
            ('SID-CHARLIE-3', 'DEFAULT', 'charlie', '3.3.3.3', '2026-11-18 15:00:00', NULL, NULL, 'ACTIVE', '2026-11-18 15:00:00', '2026-11-18 15:00:00')
        """)
        # raw events
        conn.execute("""
            INSERT INTO vpn_raw_events (fingerprint, source_file, source_line, timestamp, virtual_hub, event_type, username, session_id, raw_text, imported_at)
            VALUES
            ('fp-1', 'vpn.log', 1, '2026-11-18 10:00:00', 'DEFAULT', 'AUTH_SUCCESS', 'alice', 'SID-ALICE-1', 'auth', '2026-11-18 10:00:00'),
            ('fp-2', 'vpn.log', 2, '2026-11-18 11:00:00', 'HUB_SEC', 'AUTH_SUCCESS', 'bob', 'SID-BOB-1', 'auth', '2026-11-18 11:00:00'),
            ('fp-3', 'vpn.log', 3, '2026-11-18 08:00:00', 'DEFAULT', 'AUTH_SUCCESS', 'charlie', 'SID-CHARLIE-1', 'auth', '2026-11-18 08:00:00')
        """)

        # 2. Create Panel Users:
        # User 1: Restricted viewer to ONLY 'alice'
        conn.execute("""
            INSERT INTO panel_users (id, username, password_hash, full_name, role, is_active, created_at, allowed_vpn_users)
            VALUES (10, 'viewer_alice', ?, 'Alice Viewer', 'viewer', 1, '2026-11-18 12:00:00', ?)
        """, (hash_password("Pass123!"), json.dumps(["alice"])))

        # User 2: Unrestricted viewer (allowed_vpn_users is NULL)
        conn.execute("""
            INSERT INTO panel_users (id, username, password_hash, full_name, role, is_active, created_at, allowed_vpn_users)
            VALUES (20, 'viewer_all', ?, 'All Viewer', 'viewer', 1, '2026-11-18 12:00:00', NULL)
        """, (hash_password("Pass123!"),))

        # User 3: Superadmin
        conn.execute("""
            INSERT INTO panel_users (id, username, password_hash, full_name, role, is_active, created_at, allowed_vpn_users)
            VALUES (30, 'super_user', ?, 'Super', 'superadmin', 1, '2026-11-18 12:00:00', NULL)
        """, (hash_password("Pass123!"),))

    alice_headers = {"Authorization": f"Bearer {create_access_token({'sub': 'viewer_alice', 'role': 'viewer', 'id': 10})}"}
    all_headers = {"Authorization": f"Bearer {create_access_token({'sub': 'viewer_all', 'role': 'viewer', 'id': 20})}"}
    super_headers = {"Authorization": f"Bearer {create_access_token({'sub': 'super_user', 'role': 'superadmin', 'id': 30})}"}

    # ==========================================
    # A. Test viewer_alice (RESTRICTED TO alice)
    # ==========================================

    # 1. GET /api/sessions: should ONLY return alice's 3 sessions
    res_sess = client.get("/api/sessions", headers=alice_headers)
    assert res_sess.status_code == 200
    sess_data = res_sess.json()
    assert sess_data["total_count"] == 3
    assert all(item["username"] == "alice" for item in sess_data["items"])
    assert sess_data["summary"]["total_sessions"] == 3
    assert sess_data["summary"]["completed_sessions"] == 2
    assert sess_data["summary"]["active_sessions"] == 1

    # 2. Query String Bypass Attempt: viewer_alice requests ?username=charlie
    # MUST return 0 results!
    res_bypass = client.get("/api/sessions?username=charlie", headers=alice_headers)
    assert res_bypass.status_code == 200
    assert res_bypass.json()["total_count"] == 0
    assert len(res_bypass.json()["items"]) == 0

    # 3. GET /api/sessions/usernames: autocomplete must ONLY return alice
    res_users = client.get("/api/sessions/usernames", headers=alice_headers)
    assert res_users.status_code == 200
    assert res_users.json() == ["alice"]

    # Autocomplete query with unauthorized username
    res_users_unauth = client.get("/api/sessions/usernames?query=bob", headers=alice_headers)
    assert res_users_unauth.status_code == 200
    assert res_users_unauth.json() == []

    # 4. GET /api/dashboard/summary: scoped metrics
    res_sum = client.get("/api/dashboard/summary", headers=alice_headers)
    assert res_sum.status_code == 200
    sum_data = res_sum.json()
    assert sum_data["total_vpn_users"] == 1
    assert sum_data["total_sessions"] == 3
    assert sum_data["completed_sessions"] == 2
    assert sum_data["active_sessions"] == 1
    assert sum_data["total_duration_seconds"] == 7200  # 3600 + 3600

    # 5. GET /api/dashboard/active-sessions: only alice's active session
    res_act = client.get("/api/dashboard/active-sessions", headers=alice_headers)
    assert res_act.status_code == 200
    act_data = res_act.json()
    assert act_data["total_active"] == 1
    assert act_data["sessions"][0]["username"] == "alice"

    # 6. GET /api/dashboard/top-users: only alice
    res_top = client.get("/api/dashboard/top-users", headers=alice_headers)
    assert res_top.status_code == 200
    top_data = res_top.json()
    assert len(top_data) == 1
    assert top_data[0]["username"] == "alice"

    # 7. GET /api/dashboard/recent-events: only alice's event
    res_rec = client.get("/api/dashboard/recent-events", headers=alice_headers)
    assert res_rec.status_code == 200
    rec_data = res_rec.json()
    assert len(rec_data) == 1
    assert rec_data[0]["username"] == "alice"

    # 8. GET /api/export/csv: only contains alice
    res_csv = client.get("/api/export/csv", headers=alice_headers)
    assert res_csv.status_code == 200
    csv_text = res_csv.content.decode("utf-8-sig")
    assert "alice" in csv_text
    assert "bob" not in csv_text
    assert "charlie" not in csv_text

    # 9. GET /api/export/excel: contains alice
    res_excel = client.get("/api/export/excel", headers=alice_headers)
    assert res_excel.status_code == 200
    assert len(res_excel.content) > 1000

    # ==========================================
    # B. Test viewer_all (UNRESTRICTED VIEWER)
    # ==========================================
    res_all_sess = client.get("/api/sessions", headers=all_headers)
    assert res_all_sess.status_code == 200
    assert res_all_sess.json()["total_count"] == 7

    res_all_users = client.get("/api/sessions/usernames", headers=all_headers)
    assert res_all_users.status_code == 200
    assert sorted(res_all_users.json()) == ["alice", "bob", "charlie"]

    res_all_act = client.get("/api/dashboard/active-sessions", headers=all_headers)
    assert res_all_act.status_code == 200
    assert res_all_act.json()["total_active"] == 2  # alice and charlie

    # ==========================================
    # C. Test super_user (SUPERADMIN)
    # ==========================================
    res_super_sess = client.get("/api/sessions", headers=super_headers)
    assert res_super_sess.status_code == 200
    assert res_super_sess.json()["total_count"] == 7

    res_super_sum = client.get("/api/dashboard/summary", headers=super_headers)
    assert res_super_sum.status_code == 200
    assert res_super_sum.json()["total_vpn_users"] == 3
