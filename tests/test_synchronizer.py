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


def test_e2e_massive_securenats_and_incremental_rapid_logins(sync_env):
    """
    End-to-end regression test:
    1. Initial sync of a log file containing 4 logins + 10,000 noisy SecureNAT lines.
    2. Assert initial sync imports the 4 logins without getting stuck on SecureNAT lines.
    3. Append 4 more rapid login/logout cycles + 1 currently open login to the SAME file.
    4. Run incremental sync + correlate.
    5. Assert that total logins = 9 in vpn_sessions and exactly 1 session is currently ACTIVE.
    """
    conn, log_dir, srv_dir, sec_dir = sync_env
    sync_engine = LogSynchronizer(conn, log_dir=log_dir)

    log_file = sec_dir / "sec_20261119.log"

    # Part 1: Initial 4 logins + 10,000 SecureNAT lines
    initial_lines = []
    for i in range(1, 5):
        initial_lines.append(f'2026-11-19 12:00:{i*10:02d}.100 [HUB "DEFAULT"] Connection "CID-{i}": The new session "SID-USER-{i}" has been created. (IP address: 192.168.1.10{i}, Port number: 5000{i})\r\n')
        initial_lines.append(f'2026-11-19 12:00:{i*10+5:02d}.500 [HUB "DEFAULT"] Session "SID-USER-{i}": The session has been terminated. The statistical information is as follows: Total outgoing data size: 1000 bytes, Total incoming data size: 2000 bytes.\r\n')

    # Add 10,000 noisy SecureNAT lines
    for i in range(10000):
        initial_lines.append(f'2026-11-19 12:01:00.{i%1000:03d} [HUB "DEFAULT"] SecureNAT: Kernel IP routing table test line {i}\r\n')

    with open(log_file, "wb") as f:
        f.writelines([l.encode("utf-8") for l in initial_lines])

    stats1 = sync_engine.sync()
    assert stats1["events_imported"] == 8  # 4 creates + 4 terminates

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions")
    assert cursor.fetchone()["cnt"] == 4

    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'COMPLETED'")
    assert cursor.fetchone()["cnt"] == 4

    # Part 2: Append 4 more rapid login/logout cycles + 1 currently open login to the SAME file
    append_lines = []
    for i in range(5, 9):
        append_lines.append(f'2026-11-19 12:05:{i*10:02d}.100 [HUB "DEFAULT"] Connection "CID-{i}": The new session "SID-USER-{i}" has been created. (IP address: 192.168.1.10{i}, Port number: 5000{i})\r\n')
        append_lines.append(f'2026-11-19 12:05:{i*10+5:02d}.500 [HUB "DEFAULT"] Session "SID-USER-{i}": The session has been terminated. The statistical information is as follows: Total outgoing data size: 1500 bytes, Total incoming data size: 2500 bytes.\r\n')

    # 9th login is currently open / ACTIVE
    append_lines.append('2026-11-19 12:06:00.100 [HUB "DEFAULT"] Connection "CID-9": The new session "SID-USER-9" has been created. (IP address: 192.168.1.109, Port number: 50009)\r\n')

    with open(log_file, "ab") as f:
        f.writelines([l.encode("utf-8") for l in append_lines])

    # Run incremental sync_all() and correlate()
    sync_stats = sync_engine.sync_all()
    assert sync_stats["events_imported"] == 9  # 4 creates + 4 terminates + 1 create
    corr_stats = sync_engine.correlate()

    # Total logins must be 9
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions")
    assert cursor.fetchone()["cnt"] == 9

    # Completed must be 8
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'COMPLETED'")
    assert cursor.fetchone()["cnt"] == 8

    # Exactly 1 currently open session
    cursor.execute("SELECT session_id, username, status FROM vpn_sessions WHERE status = 'ACTIVE'")
    active_rows = cursor.fetchall()
    assert len(active_rows) == 1
    assert active_rows[0]["session_id"] == "SID-USER-9"
    assert active_rows[0]["status"] == "ACTIVE"
    assert active_rows[0]["username"] == "USER"
