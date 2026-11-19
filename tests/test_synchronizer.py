import pytest
import sqlite3
from pathlib import Path
from app.database import init_db
from app.engine.synchronizer import LogSynchronizer


@pytest.fixture
def sync_env(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    log_dir = tmp_path / "logs"
    srv_dir = log_dir / "server_log"
    sec_dir = log_dir / "security_log" / "DEFAULT"
    srv_dir.mkdir(parents=True)
    sec_dir.mkdir(parents=True)

    yield conn, log_dir, srv_dir, sec_dir
    conn.close()


def test_incremental_sync(sync_env):
    conn, log_dir, srv_dir, sec_dir = sync_env
    sync_engine = LogSynchronizer(conn, log_dir=log_dir)

    log_file = srv_dir / "vpn_20261115.log"
    
    # Step 1: Write first event
    with open(log_file, "w", encoding="utf-8") as f:
        f.write('2026-11-15 08:10:00.000 [HUB "DEFAULT"] Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)\n')

    stats1 = sync_engine.sync()
    assert stats1["files_checked"] == 1
    assert stats1["events_imported"] == 1

    # Step 2: Unchanged sync should import 0
    stats2 = sync_engine.sync()
    assert stats2["events_imported"] == 0

    # Step 3: Append second event
    with open(log_file, "a", encoding="utf-8") as f:
        f.write('2026-11-15 09:30:00.000 [HUB "DEFAULT"] Session "SID-SYNTH_ALICE-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 100 bytes, Total incoming data size: 200 bytes.\n')

    stats3 = sync_engine.sync()
    assert stats3["events_imported"] == 1

    # Verify session in DB is completed
    cursor = conn.cursor()
    cursor.execute("SELECT status, duration_seconds FROM vpn_sessions WHERE session_id = 'SID-SYNTH_ALICE-1'")
    sess = cursor.fetchone()
    assert sess["status"] == "COMPLETED"
    assert sess["duration_seconds"] == 4800


def test_diagnostics(sync_env):
    conn, log_dir, srv_dir, sec_dir = sync_env
    sync_engine = LogSynchronizer(conn, log_dir=log_dir)

    diag = sync_engine.run_diagnostics()
    assert diag["dir_exists"] is True
    assert diag["dir_readable"] is True


def test_inode_and_truncation_handling(sync_env):
    conn, log_dir, srv_dir, sec_dir = sync_env
    sync_engine = LogSynchronizer(conn, log_dir=log_dir)

    log_file = srv_dir / "vpn_current.log"

    # Step 1: Write initial line
    with open(log_file, "w", encoding="utf-8") as f:
        f.write('2026-11-15 08:10:00.000 [HUB "DEFAULT"] Connection "CID-1": The new session "SID-ALICE-1" has been created. (IP address: 10.0.0.1, Port: 50000)\n')

    stats1 = sync_engine.sync()
    assert stats1["events_imported"] == 1

    # Check sync_state
    cursor = conn.cursor()
    cursor.execute("SELECT last_byte_offset, inode FROM sync_state WHERE file_path = ?", (str(log_file.resolve()),))
    state = cursor.fetchone()
    assert state["last_byte_offset"] > 0

    # Step 2: Simulate file truncation (e.g. logrotate copytruncate)
    with open(log_file, "w", encoding="utf-8") as f:
        f.write('2026-11-15 08:20:00.000 [HUB "DEFAULT"] Connection "CID-2": The new session "SID-BOB-1" has been created. (IP address: 10.0.0.2, Port: 50001)\n')

    stats2 = sync_engine.sync()
    assert stats2["events_imported"] == 1

    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-BOB-1'")
    bob_sess = cursor.fetchone()
    assert bob_sess is not None
    assert bob_sess["username"] == "BOB"
