import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.database import init_db
from app.config import settings
from app.engine.retention import cleanup_old_raw_events


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_retention.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _insert_raw_event(conn: sqlite3.Connection, fingerprint: str, ts_str: str):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO vpn_raw_events (
            fingerprint, source_file, source_line, timestamp,
            virtual_hub, event_type, username, session_id,
            connection_id, client_ip, client_port, outgoing_bytes,
            incoming_bytes, raw_text, imported_at
        ) VALUES (?, 'server.log', 1, ?, 'DEFAULT', 'SESSION_CREATED', 'alice', 'SID-01', 'CID-01', '1.1.1.1', 1234, 100, 200, 'raw', ?)
    """, (fingerprint, ts_str, ts_str))
    conn.commit()


def test_retention_deletes_expired_raw_events_only(test_db):
    """
    Verify that raw events older than retention_days are deleted,
    while newer raw events remain completely intact.
    """
    now = datetime.now(timezone.utc)
    ts_90d_ago = (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
    ts_65d_ago = (now - timedelta(days=65)).strftime("%Y-%m-%d %H:%M:%S")
    ts_30d_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    ts_2d_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    ts_today = now.strftime("%Y-%m-%d %H:%M:%S")

    _insert_raw_event(test_db, "fp_90", ts_90d_ago)
    _insert_raw_event(test_db, "fp_65", ts_65d_ago)
    _insert_raw_event(test_db, "fp_30", ts_30d_ago)
    _insert_raw_event(test_db, "fp_2", ts_2d_ago)
    _insert_raw_event(test_db, "fp_today", ts_today)

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 5

    # Run cleanup with 60 days retention
    pruned = cleanup_old_raw_events(retention_days=60, conn=test_db)
    assert pruned == 2

    # Check remaining events
    cursor.execute("SELECT fingerprint FROM vpn_raw_events ORDER BY timestamp ASC")
    remaining_fps = [r["fingerprint"] for r in cursor.fetchall()]
    assert remaining_fps == ["fp_30", "fp_2", "fp_today"]


def test_retention_preserves_vpn_sessions_and_sync_state(test_db):
    """
    Verify that vpn_sessions (even 2+ years old), sync_state, panel_users,
    and audit_logs are 100% untouched by raw events retention.
    """
    cursor = test_db.cursor()

    # 1. Insert 2+ years old session into vpn_sessions
    two_years_ago = (datetime.now(timezone.utc) - timedelta(days=750)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO vpn_sessions (
            session_id, virtual_hub, username, client_ip, client_port,
            login_time, logout_time, duration_seconds, status,
            outgoing_bytes, incoming_bytes, created_at, updated_at
        ) VALUES (
            'SID-ANCIENT-1', 'DEFAULT', 'ancient_user', '10.0.0.1', 443,
            ?, ?, 3600, 'COMPLETED', 1048576, 2097152, ?, ?
        )
    """, (two_years_ago, two_years_ago, two_years_ago, two_years_ago))

    # 2. Insert into sync_state
    cursor.execute("""
        INSERT INTO sync_state (
            file_path, inode, last_modified, last_byte_offset,
            last_line_number, last_synced_at, status, events_count
        ) VALUES ('/var/log/ancient.log', 12345, 1700000000.0, 50000, 1000, ?, 'synced', 500)
    """, (two_years_ago,))

    # 3. Insert audit log
    cursor.execute("""
        INSERT INTO audit_logs (
            user_id, username, action, details, ip_address, created_at
        ) VALUES (1, 'superadmin', 'TEST_ACTION', 'Preserve test', '127.0.0.1', ?)
    """, (two_years_ago,))

    # 4. Insert old and new raw events
    now = datetime.now(timezone.utc)
    _insert_raw_event(test_db, "fp_old_1", (now - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S"))
    _insert_raw_event(test_db, "fp_old_2", (now - timedelta(days=80)).strftime("%Y-%m-%d %H:%M:%S"))
    _insert_raw_event(test_db, "fp_new_1", now.strftime("%Y-%m-%d %H:%M:%S"))

    test_db.commit()

    # Execute retention cleanup (60 days)
    deleted = cleanup_old_raw_events(retention_days=60, conn=test_db)
    assert deleted == 2

    # Verify vpn_sessions is 100% intact
    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-ANCIENT-1'")
    sess = cursor.fetchone()
    assert sess is not None
    assert sess["username"] == "ancient_user"
    assert sess["status"] == "COMPLETED"
    assert sess["duration_seconds"] == 3600
    assert sess["outgoing_bytes"] == 1048576

    # Verify sync_state is 100% intact
    cursor.execute("SELECT * FROM sync_state WHERE file_path = '/var/log/ancient.log'")
    sync_entry = cursor.fetchone()
    assert sync_entry is not None
    assert sync_entry["events_count"] == 500

    # Verify audit_logs is 100% intact
    cursor.execute("SELECT * FROM audit_logs WHERE action = 'TEST_ACTION'")
    audit_entry = cursor.fetchone()
    assert audit_entry is not None

    # Verify only the 1 new raw event remains
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 1


def test_retention_disabled_when_zero_or_negative(test_db):
    """
    Verify that setting retention_days to 0 (or negative) completely disables cleanup.
    """
    now = datetime.now(timezone.utc)
    ts_old = (now - timedelta(days=200)).strftime("%Y-%m-%d %H:%M:%S")

    _insert_raw_event(test_db, "fp_dis_1", ts_old)
    _insert_raw_event(test_db, "fp_dis_2", ts_old)

    # 0 disables
    deleted_zero = cleanup_old_raw_events(retention_days=0, conn=test_db)
    assert deleted_zero == 0

    # Negative disables
    deleted_neg = cleanup_old_raw_events(retention_days=-30, conn=test_db)
    assert deleted_neg == 0

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 2


def test_retention_batching(test_db):
    """
    Verify that deletion in small batches (e.g. 50 items) properly cleans up
    all matching items across multiple iterations and commits safely.
    """
    now = datetime.now(timezone.utc)
    ts_old = (now - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")

    # Insert 125 expired rows
    for i in range(125):
        _insert_raw_event(test_db, f"fp_batch_{i}", ts_old)

    cursor = test_db.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 125

    # Run cleanup with batch_size=50 (will take 3 iterations: 50 + 50 + 25)
    deleted = cleanup_old_raw_events(retention_days=60, conn=test_db, batch_size=50)
    assert deleted == 125

    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 0


def test_settings_retention_configuration():
    """
    Verify settings.RAW_EVENTS_RETENTION_DAYS default and accessibility.
    """
    assert hasattr(settings, "RAW_EVENTS_RETENTION_DAYS")
    assert settings.RAW_EVENTS_RETENTION_DAYS == 60
