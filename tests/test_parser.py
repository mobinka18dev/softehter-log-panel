import pytest
from app.engine.parser import parse_line, extract_hub_from_path
from app.engine.models import EventType


def test_extract_hub_from_path():
    assert extract_hub_from_path("/var/log/vpnserver/security_log/DEFAULT/sec_20261118.log") == "DEFAULT"
    assert extract_hub_from_path("C:\\logs\\security_log\\OFFICE\\sec_20261118.log") == "OFFICE"
    assert extract_hub_from_path("/var/log/vpnserver/server_log/vpn_20261118.log") == "DEFAULT"


def test_parse_server_start_stop():
    line_start = "2026-11-15 08:00:00.000 The SoftEther VPN Server service has started."
    ev = parse_line(line_start, "vpn.log", 1)
    assert ev is not None
    assert ev.event_type == EventType.SERVER_START
    assert ev.virtual_hub == "SERVER"
    assert ev.timestamp == "2026-11-15 08:00:00.000"

    line_stop = "2026-11-15 23:59:59.000 The SoftEther VPN Server service has stopped."
    ev_stop = parse_line(line_stop, "vpn.log", 2)
    assert ev_stop is not None
    assert ev_stop.event_type == EventType.SERVER_STOP


def test_parse_auth_success():
    line = '2026-11-15 08:10:00.300 [HUB "DEFAULT"] Connection "CID-101": Successfully authenticated as user "synth_alice".'
    ev = parse_line(line, "vpn.log", 5)
    assert ev is not None
    assert ev.event_type == EventType.AUTH_SUCCESS
    assert ev.virtual_hub == "DEFAULT"
    assert ev.connection_id == "CID-101"
    assert ev.username == "synth_alice"


def test_parse_session_created():
    line = '2026-11-15 08:10:00.350 [HUB "DEFAULT"] Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321, Physical underlying protocol: "Standard TCP/IP (IPv4)")'
    ev = parse_line(line, "vpn.log", 6)
    assert ev is not None
    assert ev.event_type == EventType.SESSION_CREATED
    assert ev.session_id == "SID-SYNTH_ALICE-1"
    assert ev.client_ip == "198.51.100.10"
    assert ev.client_port == 54321
    assert ev.username == "SYNTH_ALICE"


def test_parse_session_terminated():
    line = '2026-11-15 09:30:00.800 [HUB "DEFAULT"] Session "SID-SYNTH_ALICE-1": The session has been terminated. The statistical information is as follows: Total outgoing data size: 10485760 bytes, Total incoming data size: 20971520 bytes.'
    ev = parse_line(line, "vpn.log", 7)
    assert ev is not None
    assert ev.event_type == EventType.SESSION_TERMINATED
    assert ev.session_id == "SID-SYNTH_ALICE-1"
    assert ev.outgoing_bytes == 10485760
    assert ev.incoming_bytes == 20971520


def test_parse_auth_attempt_and_ip():
    line = '2026-11-15 08:10:00.250 [HUB "DEFAULT"] The connection "CID-101" (Client IP address: 198.51.100.10, Port: 54321) is attempting to connect to the Virtual Hub. The auth type provided is "Password authentication" and the user name is "synth_alice".'
    ev = parse_line(line, "vpn.log", 4)
    assert ev is not None
    assert ev.connection_id == "CID-101"
    assert ev.client_ip == "198.51.100.10"
    assert ev.client_port == 54321
    assert ev.username == "synth_alice"


def test_fingerprint_deduplication():
    line1 = '2026-11-15 08:10:00.350 [HUB "DEFAULT"] Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)'
    line2 = '2026-11-15 08:10:00.350 Connection "CID-101": The new session "SID-SYNTH_ALICE-1" has been created. (IP address: 198.51.100.10, Port: 54321)'
    
    ev1 = parse_line(line1, "server_log.log", 10)
    ev2 = parse_line(line2, "security_log.log", 20, default_hub="DEFAULT")

    assert ev1 is not None and ev2 is not None
    assert ev1.fingerprint == ev2.fingerprint
