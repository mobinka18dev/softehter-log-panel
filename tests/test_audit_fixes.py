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


def test_stale_active_sessions_timeout(memory_db):
    correlator = SessionCorrelator(memory_db)

    # User connects on Day 1
    l1 = '2026-11-01 08:00:00.000 [HUB "DEFAULT"] Connection "CID-601": The new session "SID-SYNTH_STALE-1" has been created. (IP address: 198.51.100.22, Port: 50000)'
    ev1 = parse_line(l1, "server.log", 1)
    correlator.process_events([ev1])

    # Session should initially be ACTIVE
    cursor = memory_db.cursor()
    cursor.execute("SELECT status FROM vpn_sessions WHERE session_id = 'SID-SYNTH_STALE-1'")
    assert cursor.fetchone()["status"] == SessionStatus.ACTIVE.value

    # Day 3 comes (more than 24h later) with a new event from another user
    l2 = '2026-11-03 10:00:00.000 [HUB "DEFAULT"] Connection "CID-602": The new session "SID-SYNTH_OTHER-1" has been created. (IP address: 198.51.100.33, Port: 50001)'
    ev2 = parse_line(l2, "server.log", 2)
    correlator.process_events([ev2])

    # Stale session should now be automatically marked INCOMPLETE without fabricating logout time
    cursor.execute("SELECT status, logout_time, status_reason FROM vpn_sessions WHERE session_id = 'SID-SYNTH_STALE-1'")
    stale_sess = cursor.fetchone()
    assert stale_sess["status"] == SessionStatus.INCOMPLETE.value
    assert stale_sess["logout_time"] is None  # Never fabricate logout time!
    assert "exceeded 24h active window" in stale_sess["status_reason"]


def test_root_wrapper_scripts_exist():
    root = Path(__file__).parent.parent
    for script_name in ["install.sh", "update.sh", "uninstall.sh", "backup.sh", "restore.sh"]:
        p = root / script_name
        assert p.exists(), f"Root wrapper script '{script_name}' is missing"
        content = p.read_text(encoding="utf-8")
        assert f"deploy/{script_name}" in content
