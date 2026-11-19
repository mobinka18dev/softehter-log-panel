import pytest
import sqlite3
from app.database import init_db
from app.engine.correlator import SessionCorrelator
from app.engine.parser import parse_line
from app.engine.models import SessionStatus


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_correlate_completed_session(memory_db):
    correlator = SessionCorrelator(memory_db)

    line1 = '2026-11-15 08:10:00.000 [HUB "DEFAULT"] Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)'
    line2 = '2026-11-15 09:30:00.000 [HUB "DEFAULT"] Session "SID-SYNTH_ALICE-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 1000 bytes, Total incoming data size: 2000 bytes.'

    ev1 = parse_line(line1, "server.log", 1)
    ev2 = parse_line(line2, "server.log", 2)

    correlator.process_events([ev1, ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-SYNTH_ALICE-1'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.COMPLETED.value
    assert sess["duration_seconds"] == 4800  # 1h 20m = 80 minutes = 4800s
    assert sess["client_ip"] == "198.51.100.10"
    assert sess["outgoing_bytes"] == 1000
    assert sess["incoming_bytes"] == 2000
    assert sess["confidence_score"] == 1.0


def test_correlate_multiple_simultaneous_sessions(memory_db):
    correlator = SessionCorrelator(memory_db)

    # Bob connects from Laptop
    l1 = '2026-11-15 10:00:00.000 [HUB "DEFAULT"] Connection "CID-102": The new session "SID-SYNTH_BOB-1" has been created. (IP address: 203.0.113.25, Port: 51234)'
    # Bob connects simultaneously from Phone
    l2 = '2026-11-15 10:05:00.000 [HUB "DEFAULT"] Connection "CID-103": The new session "SID-SYNTH_BOB-2" has been created. (IP address: 192.0.2.77, Port: 59876)'

    # Bob disconnects Laptop
    l3 = '2026-11-15 11:00:00.000 [HUB "DEFAULT"] Session "SID-SYNTH_BOB-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 500 bytes, Total incoming data size: 500 bytes.'
    # Bob disconnects Phone
    l4 = '2026-11-15 11:30:00.000 [HUB "DEFAULT"] Session "SID-SYNTH_BOB-2": The session has been terminated. The statistical information is as follows: Total outgoing data size: 600 bytes, Total incoming data size: 600 bytes.'

    events = [parse_line(x, "server.log", i) for i, x in enumerate([l1, l2, l3, l4], 1)]
    correlator.process_events(events)

    cursor = memory_db.cursor()
    cursor.execute("SELECT * FROM vpn_sessions WHERE username = 'SYNTH_BOB' ORDER BY session_id ASC")
    rows = cursor.fetchall()

    assert len(rows) == 2
    assert rows[0]["session_id"] == "SID-SYNTH_BOB-1"
    assert rows[0]["client_ip"] == "203.0.113.25"
    assert rows[0]["duration_seconds"] == 3600  # 1 hour

    assert rows[1]["session_id"] == "SID-SYNTH_BOB-2"
    assert rows[1]["client_ip"] == "192.0.2.77"
    assert rows[1]["duration_seconds"] == 5100  # 1h 25m = 5100s


def test_correlate_server_restart_interruption(memory_db):
    correlator = SessionCorrelator(memory_db)

    # Charlie connects
    l1 = '2026-11-15 14:00:00.000 [HUB "OFFICE"] Connection "CID-201": The new session "SID-SYNTH_CHARLIE-1" has been created. (IP address: 198.51.100.50, Port: 60123)'
    # Server restarts at 15:00:00 without normal logout
    l2 = '2026-11-15 15:00:00.000 The SoftEther VPN Server service has started.'

    ev1 = parse_line(l1, "server.log", 1)
    ev2 = parse_line(l2, "server.log", 2)

    correlator.process_events([ev1, ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-SYNTH_CHARLIE-1'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.INCOMPLETE.value
    assert "restart" in sess["status_reason"].lower()
    assert sess["duration_seconds"] == 3600  # Duration calculated up to restart
    assert sess["logout_time"] == "2026-11-15 15:00:00.000"


def test_correlate_orphaned_logout(memory_db):
    correlator = SessionCorrelator(memory_db)

    # Only termination line exists (missing login)
    line = '2026-11-15 12:00:00.000 Session "SID-SYNTH_ORPHAN-99": The session has been terminated. The statistical information is as follows: Total outgoing data size: 1024 bytes, Total incoming data size: 2048 bytes.'
    ev = parse_line(line, "security.log", 1, default_hub="DEFAULT")

    correlator.process_events([ev])

    cursor = memory_db.cursor()
    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-SYNTH_ORPHAN-99'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.INCOMPLETE.value
    assert "Missing login" in sess["status_reason"]
    assert sess["login_time"] is None
    assert sess["logout_time"] == "2026-11-15 12:00:00.000"
    assert sess["confidence_score"] == 0.5


def test_correlate_duplicate_events_server_and_security(memory_db):
    correlator = SessionCorrelator(memory_db)

    # Identical session events recorded in both server_log and security_log
    s_line1 = '2026-11-15 08:10:00.350 [HUB "DEFAULT"] Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)'
    sec_line1 = '2026-11-15 08:10:00.350 Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)'

    ev_srv = parse_line(s_line1, "server_log.log", 1)
    ev_sec = parse_line(sec_line1, "sec_20261115.log", 1, default_hub="DEFAULT")

    correlator.process_events([ev_srv])
    correlator.process_events([ev_sec])

    cursor = memory_db.cursor()
    # Must only have 1 raw event stored (deduplicated)
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
    assert cursor.fetchone()["cnt"] == 1

    # Must only have 1 session stored
    cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions")
    assert cursor.fetchone()["cnt"] == 1


def test_correlate_rapid_consecutive_connections_same_user(memory_db):
    """
    Test rapid repeated connections/disconnections from the same user (e.g. 8 times).
    Ensures that rapid reconnects are not skipped, collided, or dropped across server_log and security_log.
    """
    correlator = SessionCorrelator(memory_db)
    events = []

    # 8 rapid connections and disconnections
    for i in range(1, 9):
        cid = f"CID-{3000 + i}"
        sid = f"SID-RAASANO-[OPENVPN_L3]-{i}"
        port = 50000 + i
        sec_start = f"{i*2:02d}"
        sec_end = f"{i*2 + 1:02d}"

        # 1. Auth in server_log (no HUB prefix)
        auth_line = f'2026-11-18 16:15:{sec_start}.100 Connection "{cid}": Successfully authenticated as user "raasano".'
        events.append(parse_line(auth_line, "vpn_server.log", i * 4 - 3, default_hub="DEFAULT"))

        # 2. Session created in security_log (with HUB "HUB" prefix)
        sess_create_line = f'2026-11-18 16:15:{sec_start}.200 [HUB "HUB"] Connection "{cid}": The new session "{sid}" has been created. (IP address: 91.92.208.200, Port number: {port}, Physical underlying protocol: "Legacy VPN - OPENVPN_L3")'
        events.append(parse_line(sess_create_line, "security_log/sec_20261118.log", i * 4 - 2, default_hub="HUB"))

        # For the first 7, disconnect them; the 8th remains ACTIVE
        if i < 8:
            term_line = f'2026-11-18 16:15:{sec_end}.500 [HUB "HUB"] Session "{sid}": The session has been terminated. The statistical information is as follows: Total outgoing data size: 5000 bytes, Total incoming data size: 8000 bytes.'
            events.append(parse_line(term_line, "security_log/sec_20261118.log", i * 4 - 1, default_hub="HUB"))

    correlator.process_events(events)

    cursor = memory_db.cursor()
    cursor.execute("SELECT session_id, username, virtual_hub, status FROM vpn_sessions ORDER BY id ASC")
    sessions = cursor.fetchall()

    # All 8 sessions must be recorded
    assert len(sessions) == 8, f"Expected 8 sessions but found {len(sessions)}"

    for idx, s in enumerate(sessions, 1):
        assert s["username"] == "raasano"
        assert s["virtual_hub"] == "HUB"
        if idx < 8:
            assert s["status"] == SessionStatus.COMPLETED.value
        else:
            assert s["status"] == SessionStatus.ACTIVE.value
