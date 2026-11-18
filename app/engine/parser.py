from pathlib import Path
from app.engine.models import RawLogEvent, EventType
from app.engine import patterns


def extract_hub_from_path(file_path: str | Path) -> str:
    """
    Extract virtual hub name from file path if it is inside security_log/<HUB_NAME>/.
    e.g. /var/log/vpnserver/security_log/DEFAULT/sec_20261118.log -> "DEFAULT"
    """
    p = Path(file_path)
    parts = p.parts
    for i, part in enumerate(parts):
        if part.lower() == "security_log" and i + 1 < len(parts) - 1:
            return parts[i + 1].upper()
    return "DEFAULT"


def parse_line(
    raw_line: str,
    source_file: str,
    line_no: int,
    default_hub: str | None = None
) -> RawLogEvent | None:
    """
    Parse a single line from a SoftEther log file into a normalized RawLogEvent.
    Returns None if the line does not match recognized SoftEther event formats.
    """
    line = raw_line.strip()
    if not line:
        return None

    # 1. Match timestamp
    ts_match = patterns.RE_TIMESTAMP.match(line)
    if not ts_match:
        return None

    timestamp = ts_match.group(1)
    message = ts_match.group(2).strip()

    # 2. Extract HUB prefix if present in the message
    virtual_hub = default_hub or "DEFAULT"
    hub_match = patterns.RE_HUB_PREFIX.match(message)
    if hub_match:
        virtual_hub = hub_match.group(1).upper()
        message = hub_match.group(2).strip()

    # 3. Check Server Start / Stop
    if patterns.RE_SERVER_START.search(message):
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub="SERVER",
            event_type=EventType.SERVER_START,
            raw_text=raw_line
        )

    if patterns.RE_SERVER_STOP.search(message):
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub="SERVER",
            event_type=EventType.SERVER_STOP,
            raw_text=raw_line
        )

    # 4. Check Session Terminated
    term_match = patterns.RE_SESSION_TERMINATED.search(message)
    if term_match:
        session_id = term_match.group(1)
        out_bytes = int(term_match.group(2)) if term_match.group(2) else 0
        in_bytes = int(term_match.group(3)) if term_match.group(3) else 0
        username = None
        sid_match = patterns.RE_SID_USERNAME.match(session_id)
        if sid_match:
            username = sid_match.group(1)

        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.SESSION_TERMINATED,
            session_id=session_id,
            username=username,
            outgoing_bytes=out_bytes,
            incoming_bytes=in_bytes,
            raw_text=raw_line
        )

    # 5. Check Session Created
    sess_match = patterns.RE_SESSION_CREATED_1.search(message)
    if sess_match:
        cid = f"CID-{sess_match.group(1)}" if sess_match.group(1) else None
        session_id = sess_match.group(2)
        ip = sess_match.group(3)
        port = int(sess_match.group(4)) if sess_match.group(4) else None
        username = None
        sid_match = patterns.RE_SID_USERNAME.match(session_id)
        if sid_match:
            username = sid_match.group(1)

        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.SESSION_CREATED,
            session_id=session_id,
            connection_id=cid,
            client_ip=ip,
            client_port=port,
            username=username,
            raw_text=raw_line
        )

    sess_match2 = patterns.RE_SESSION_CREATED_2.search(message)
    if sess_match2:
        session_id = sess_match2.group(1)
        username = None
        sid_match = patterns.RE_SID_USERNAME.match(session_id)
        if sid_match:
            username = sid_match.group(1)

        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.SESSION_CREATED,
            session_id=session_id,
            username=username,
            raw_text=raw_line
        )

    # 6. Check Authentication Success
    auth_m1 = patterns.RE_AUTH_SUCCESS_1.search(message)
    if auth_m1:
        cid = f"CID-{auth_m1.group(1)}"
        username = auth_m1.group(2)
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.AUTH_SUCCESS,
            connection_id=cid,
            username=username,
            raw_text=raw_line
        )

    auth_m2 = patterns.RE_AUTH_SUCCESS_2.search(message)
    if auth_m2:
        cid = f"CID-{auth_m2.group(1)}"
        username = auth_m2.group(2)
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.AUTH_SUCCESS,
            connection_id=cid,
            username=username,
            raw_text=raw_line
        )

    auth_m3 = patterns.RE_AUTH_SUCCESS_3.search(message)
    if auth_m3:
        username = auth_m3.group(1)
        ip = auth_m3.group(2)
        port = int(auth_m3.group(3)) if auth_m3.group(3) else None
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.AUTH_SUCCESS,
            username=username,
            client_ip=ip,
            client_port=port,
            raw_text=raw_line
        )

    # 7. Check Auth Attempt (contains IP, port, CID, username before auth success/session)
    attempt_m = patterns.RE_AUTH_ATTEMPT.search(message)
    if attempt_m:
        cid = f"CID-{attempt_m.group(1)}"
        ip = attempt_m.group(2)
        port = int(attempt_m.group(3)) if attempt_m.group(3) else None
        username = attempt_m.group(4)
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.AUTH_SUCCESS,
            connection_id=cid,
            client_ip=ip,
            client_port=port,
            username=username,
            raw_text=raw_line
        )

    # 8. Check Auth Fail
    fail_m1 = patterns.RE_AUTH_FAIL_1.search(message)
    if fail_m1:
        cid = f"CID-{fail_m1.group(1)}"
        user = fail_m1.group(2)
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.AUTH_FAIL,
            connection_id=cid,
            username=user,
            raw_text=raw_line
        )

    # 9. Check Connection Created
    conn_c1 = patterns.RE_CONN_CREATED_1.search(message)
    if conn_c1:
        ip = conn_c1.group(1)
        port = int(conn_c1.group(2))
        cid = f"CID-{conn_c1.group(3)}"
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.CONN_CREATED,
            connection_id=cid,
            client_ip=ip,
            client_port=port,
            raw_text=raw_line
        )

    conn_c2 = patterns.RE_CONN_CREATED_2.search(message)
    if conn_c2:
        cid = f"CID-{conn_c2.group(1)}"
        ip = conn_c2.group(2)
        port = int(conn_c2.group(3))
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.CONN_CREATED,
            connection_id=cid,
            client_ip=ip,
            client_port=port,
            raw_text=raw_line
        )

    # 10. Check Connection Terminated
    conn_t1 = patterns.RE_CONN_TERMINATED_2.search(message)
    if conn_t1:
        cid = f"CID-{conn_t1.group(1)}"
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.CONN_TERMINATED,
            connection_id=cid,
            raw_text=raw_line
        )

    conn_t2 = patterns.RE_CONN_TERMINATED_1.search(message)
    if conn_t2:
        cid = f"CID-{conn_t2.group(1)}"
        return RawLogEvent(
            source_file=source_file,
            source_line=line_no,
            timestamp=timestamp,
            virtual_hub=virtual_hub,
            event_type=EventType.CONN_TERMINATED,
            connection_id=cid,
            raw_text=raw_line
        )

    return None
