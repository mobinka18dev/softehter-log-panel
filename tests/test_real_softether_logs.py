import pytest
from app.engine.parser import parse_line
from app.engine.models import EventType
from app.engine.correlator import SessionCorrelator
from app.database import init_db
import sqlite3


def test_real_softether_auth_event():
    # 1. With HUB prefix
    line1 = '2026-11-18 16:15:39.750 [HUB "HUB"] Connection "CID-3631": Successfully authenticated as user "raasano".'
    ev1 = parse_line(line1, "server.log", 1)
    assert ev1 is not None
    assert ev1.event_type == EventType.AUTH_SUCCESS
    assert ev1.virtual_hub == "HUB"
    assert ev1.connection_id == "CID-3631"
    assert ev1.username == "raasano"
    assert ev1.timestamp == "2026-11-18 16:15:39.750"

    # 2. Without HUB prefix (security_log in HUB subfolder)
    line2 = '2026-11-18 16:15:39.750 Connection "CID-3631": Successfully authenticated as user "raasano".'
    ev2 = parse_line(line2, "sec_20261118.log", 1, default_hub="HUB")
    assert ev2 is not None
    assert ev2.event_type == EventType.AUTH_SUCCESS
    assert ev2.virtual_hub == "HUB"
    assert ev2.connection_id == "CID-3631"
    assert ev2.username == "raasano"


def test_real_softether_session_created_with_brackets():
    line = '2026-11-18 16:15:39.750 [HUB "HUB"] Connection "CID-3631": The new session "SID-RAASANO-[OPENVPN_L3]-58" has been created. (IP address: 91.92.208.200, Port number: 50095, Physical underlying protocol: "Legacy VPN - OPENVPN_L3")'
    ev = parse_line(line, "server.log", 2)
    assert ev is not None
    assert ev.event_type == EventType.SESSION_CREATED
    assert ev.virtual_hub == "HUB"
    assert ev.connection_id == "CID-3631"
    assert ev.session_id == "SID-RAASANO-[OPENVPN_L3]-58"
    assert ev.client_ip == "91.92.208.200"
    assert ev.client_port == 50095
    assert ev.username.lower() == "raasano"


def test_real_softether_client_details_event():
    line = '2026-11-18 16:15:39.750 [HUB "HUB"] Session "SID-RAASANO-[OPENVPN_L3]-58": VPN Client details: (Client product name: "OpenVPN Client", Client version: 441, Client build number: 9782, Server product name: "SoftEther VPN Server (64 bit)", Server version: 441, Server build number: 9782, Client OS name: "OpenVPN Client", Client OS version: "-", Client product ID: "-", Client host name: "", Client IP address: "91.92.208.200", Client port number: 50095, Server host name: "192.168.5.6", Server IP address: "192.168.5.6", Server port number: 1198, Proxy host name: "", Proxy IP address: "0.0.0.0", Proxy port number: 0, Virtual Hub name: "HUB", Client unique ID: "187DA2E99E3905DB3F3E587B6CC47875")'
    ev = parse_line(line, "server.log", 3)
    assert ev is not None
    assert ev.session_id == "SID-RAASANO-[OPENVPN_L3]-58"
    assert ev.client_ip == "91.92.208.200"
    assert ev.client_port == 50095
    assert ev.virtual_hub == "HUB"
    assert ev.username.lower() == "raasano"


def test_real_softether_session_terminated_and_bytes():
    line = '2026-11-18 16:15:03.670 [HUB "HUB"] Session "SID-RAASANO-[OPENVPN_L3]-57": The session has been terminated. The statistical information is as follows: Total outgoing data size: 233820 bytes, Total incoming data size: 71586 bytes.'
    ev = parse_line(line, "server.log", 4)
    assert ev is not None
    assert ev.event_type == EventType.SESSION_TERMINATED
    assert ev.session_id == "SID-RAASANO-[OPENVPN_L3]-57"
    assert ev.virtual_hub == "HUB"
    assert ev.outgoing_bytes == 233820
    assert ev.incoming_bytes == 71586
    assert ev.username.lower() == "raasano"


def test_fast_ignore_securenats():
    lines = [
        '2026-11-18 16:15:39.750 [HUB "HUB"] SecureNAT: The UDP session 1 has been created.',
        '2026-11-18 16:15:39.750 [HUB "HUB"] SecureNAT: The TCP session 2 has been terminated.',
        '2026-11-18 16:15:39.750 [HUB "HUB"] Session "SID-SECURENAT-1": The session has been created.',
        '2026-11-18 16:15:39.750 [HUB "HUB"] Session "SID-SECURENAT-1": The session has been terminated.'
    ]
    for line in lines:
        ev = parse_line(line, "server.log", 10)
        assert ev is None


def test_end_to_end_real_log_correlation():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    correlator = SessionCorrelator(conn)

    lines = [
        '2026-11-18 16:10:00.000 [HUB "HUB"] Connection "CID-3631": Successfully authenticated as user "raasano".',
        '2026-11-18 16:10:00.500 [HUB "HUB"] Connection "CID-3631": The new session "SID-RAASANO-[OPENVPN_L3]-58" has been created. (IP address: 91.92.208.200, Port number: 50095, Physical underlying protocol: "Legacy VPN - OPENVPN_L3")',
        '2026-11-18 16:15:03.670 [HUB "HUB"] Session "SID-RAASANO-[OPENVPN_L3]-58": The session has been terminated. The statistical information is as follows: Total outgoing data size: 233820 bytes, Total incoming data size: 71586 bytes.'
    ]

    events = [parse_line(l, "server.log", idx) for idx, l in enumerate(lines, 1)]
    valid_events = [e for e in events if e is not None]
    assert len(valid_events) == 3

    correlator.process_events(valid_events)

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vpn_sessions WHERE session_id = 'SID-RAASANO-[OPENVPN_L3]-58'")
    session = cursor.fetchone()

    assert session is not None
    assert session["username"] == "raasano"
    assert session["virtual_hub"] == "HUB"
    assert session["client_ip"] == "91.92.208.200"
    assert session["client_port"] == 50095
    assert session["status"] == "COMPLETED"
    assert session["outgoing_bytes"] == 233820
    assert session["incoming_bytes"] == 71586
    assert session["duration_seconds"] == 303  # 16:10:00 to 16:15:03 -> ~303s
