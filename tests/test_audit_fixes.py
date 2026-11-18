import pytest
import sqlite3
from pathlib import Path
from app.database import init_db
from app.engine.parser import parse_line
from app.engine.correlator import SessionCorrelator
from app.engine.models import SessionStatus, EventType


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_timestamp_slash_format():
    line = '2026/11/18 10:15:30.123 [HUB "DEFAULT"] Connection "CID-501": Successfully authenticated as user "synth_slash_user".'
    ev = parse_line(line, "server.log", 1)
    assert ev is not None
    assert ev.timestamp == "2026/11/18 10:15:30.123"
    assert ev.username == "synth_slash_user"
    assert ev.event_type == EventType.AUTH_SUCCESS


def test_ipv6_address_parsing():
    line = '2026-11-18 10:20:00.000 [HUB "DEFAULT"] Connection "CID-502": The new session "SID-SYNTH_IPV6-1" has been created. (IP address: 2001:db8:85a3::8a2e:370:7334, Port: 443)'
    ev = parse_line(line, "server.log", 1)
    assert ev is not None
    assert ev.client_ip == "2001:db8:85a3::8a2e:370:7334"
    assert ev.client_port == 443


def test_root_wrapper_scripts_exist():
    root = Path(__file__).parent.parent
    for script_name in ["install.sh", "update.sh", "uninstall.sh", "backup.sh", "restore.sh"]:
        p = root / script_name
        assert p.exists(), f"Root wrapper script '{script_name}' is missing"
        content = p.read_text(encoding="utf-8")
        assert f"deploy/{script_name}" in content


# =========================================================================
# TASK 1 SPECIFIC TESTS
# =========================================================================

def test_legitimately_active_session_lasting_72_hours(memory_db):
    """
    1. A legitimately active session lasting 72 hours.
    Must NOT be marked disconnected simply because it exceeded 24 hours.
    Must remain ACTIVE with no fabricated logout time.
    """
    correlator = SessionCorrelator(memory_db)

    # Session created at Day 1 08:00
    l1 = '2026-11-15 08:00:00.000 [HUB "DEFAULT"] Connection "CID-701": The new session "SID-SYNTH_LONG_ACTIVE-1" has been created. (IP address: 198.51.100.44, Port: 45000)'
    ev1 = parse_line(l1, "server.log", 1)
    correlator.process_events([ev1])

    # 72 hours later (Day 4 08:00), newer logs arrive from other operations
    l2 = '2026-11-18 08:00:00.000 [HUB "DEFAULT"] Connection "CID-702": Successfully authenticated as user "synth_other".'
    ev2 = parse_line(l2, "server.log", 2)
    correlator.process_events([ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT status, logout_time, duration_seconds FROM vpn_sessions WHERE session_id = 'SID-SYNTH_LONG_ACTIVE-1'")
    sess = cursor.fetchone()

    assert sess is not None
    # Must remain ACTIVE (72 hours is completely legitimate for long active sessions)
    assert sess["status"] == SessionStatus.ACTIVE.value
    assert sess["logout_time"] is None
    assert sess["duration_seconds"] is None


def test_old_session_without_logout_event(memory_db):
    """
    2. An old session without a logout event.
    When logs continue across extended historical threshold (> 7 days) without any logout or server event,
    its status cannot be verified and must explicitly be marked UNVERIFIED.
    No fabricated logout time or duration.
    """
    correlator = SessionCorrelator(memory_db)

    # Session created on 2026-11-01
    l1 = '2026-11-01 08:00:00.000 [HUB "DEFAULT"] Connection "CID-801": The new session "SID-SYNTH_UNVERIFIED-1" has been created. (IP address: 198.51.100.55, Port: 46000)'
    ev1 = parse_line(l1, "server.log", 1)
    correlator.process_events([ev1])

    # Historical logs continue 14 days later on 2026-11-15 with no logout event found
    l2 = '2026-11-15 10:00:00.000 [HUB "DEFAULT"] Connection "CID-802": The new session "SID-SYNTH_NEW-1" has been created. (IP address: 198.51.100.66, Port: 47000)'
    ev2 = parse_line(l2, "server.log", 2)
    correlator.process_events([ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT status, logout_time, duration_seconds, status_reason FROM vpn_sessions WHERE session_id = 'SID-SYNTH_UNVERIFIED-1'")
    sess = cursor.fetchone()

    assert sess is not None
    # Must be UNVERIFIED (never fabricate logout time, never guess disconnected)
    assert sess["status"] == SessionStatus.UNVERIFIED.value
    assert sess["logout_time"] is None
    assert sess["duration_seconds"] is None
    assert "cannot be verified" in sess["status_reason"]


def test_session_with_confirmed_logout(memory_db):
    """
    3. A session with a confirmed logout.
    Must be marked COMPLETED with exact duration calculated.
    """
    correlator = SessionCorrelator(memory_db)

    l1 = '2026-11-15 08:00:00.000 [HUB "DEFAULT"] Connection "CID-901": The new session "SID-SYNTH_CONFIRMED-1" has been created. (IP address: 198.51.100.77, Port: 48000)'
    l2 = '2026-11-15 10:30:00.000 [HUB "DEFAULT"] Session "SID-SYNTH_CONFIRMED-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 1024 bytes, Total incoming data size: 2048 bytes.'

    ev1 = parse_line(l1, "server.log", 1)
    ev2 = parse_line(l2, "server.log", 2)
    correlator.process_events([ev1, ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT status, login_time, logout_time, duration_seconds FROM vpn_sessions WHERE session_id = 'SID-SYNTH_CONFIRMED-1'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.COMPLETED.value
    assert sess["login_time"] == "2026-11-15 08:00:00.000"
    assert sess["logout_time"] == "2026-11-15 10:30:00.000"
    assert sess["duration_seconds"] == 9000  # 2 hours 30 mins = 9000s


def test_session_interrupted_by_server_restart(memory_db):
    """
    4. A session interrupted by a confirmed server restart.
    Must be marked INCOMPLETE with server restart reason and exact restart timestamp.
    """
    correlator = SessionCorrelator(memory_db)

    l1 = '2026-11-15 12:00:00.000 [HUB "DEFAULT"] Connection "CID-950": The new session "SID-SYNTH_RESTART-1" has been created. (IP address: 198.51.100.88, Port: 49000)'
    l2 = '2026-11-15 13:00:00.000 The SoftEther VPN Server service has started.'

    ev1 = parse_line(l1, "server.log", 1)
    ev2 = parse_line(l2, "server.log", 2)
    correlator.process_events([ev1, ev2])

    cursor = memory_db.cursor()
    cursor.execute("SELECT status, logout_time, status_reason FROM vpn_sessions WHERE session_id = 'SID-SYNTH_RESTART-1'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.INCOMPLETE.value
    assert "VPN Server restart at 2026-11-15 13:00:00.000" in sess["status_reason"]
    assert sess["logout_time"] == "2026-11-15 13:00:00.000"


def test_session_with_missing_historical_login_data(memory_db):
    """
    5. A session with missing historical login data.
    Termination log exists, but login happened before log retention period.
    Must be marked INCOMPLETE, login_time is None, logout_time is preserved.
    """
    correlator = SessionCorrelator(memory_db)

    l1 = '2026-11-15 09:00:00.000 Session "SID-SYNTH_MISSING_LOGIN-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 5000 bytes, Total incoming data size: 10000 bytes.'
    ev1 = parse_line(l1, "security.log", 1, default_hub="DEFAULT")
    correlator.process_events([ev1])

    cursor = memory_db.cursor()
    cursor.execute("SELECT status, login_time, logout_time, duration_seconds, status_reason FROM vpn_sessions WHERE session_id = 'SID-SYNTH_MISSING_LOGIN-1'")
    sess = cursor.fetchone()

    assert sess is not None
    assert sess["status"] == SessionStatus.INCOMPLETE.value
    assert sess["login_time"] is None
    assert sess["logout_time"] == "2026-11-15 09:00:00.000"
    assert sess["duration_seconds"] is None
    assert "Missing login event" in sess["status_reason"]
