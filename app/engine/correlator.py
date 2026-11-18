from datetime import datetime, timezone
import sqlite3
from app.engine.models import (
    RawLogEvent,
    EventType,
    CorrelatedSession,
    SessionStatus
)


class SessionCorrelator:
    """
    Session correlation engine.
    Processes normalized raw events and maintains stateful VPN sessions.
    """

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn

    def process_events(self, events: list[RawLogEvent]) -> int:
        """
        Process a batch of RawLogEvents:
        1. Insert deduplicated events into vpn_raw_events.
        2. Correlate events into vpn_sessions.
        Returns count of newly inserted events.
        """
        if not events:
            return 0

        cursor = self.conn.cursor()
        new_event_count = 0
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 1. Insert raw events (ignoring duplicates via UNIQUE fingerprint)
        for ev in events:
            try:
                cursor.execute("""
                    INSERT INTO vpn_raw_events (
                        fingerprint, source_file, source_line, timestamp,
                        virtual_hub, event_type, username, session_id,
                        connection_id, client_ip, client_port, outgoing_bytes,
                        incoming_bytes, raw_text, imported_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ev.fingerprint, ev.source_file, ev.source_line, ev.timestamp,
                    ev.virtual_hub, ev.event_type.value, ev.username, ev.session_id,
                    ev.connection_id, ev.client_ip, ev.client_port, ev.outgoing_bytes,
                    ev.incoming_bytes, ev.raw_text, now_iso
                ))
                new_event_count += 1
            except sqlite3.IntegrityError:
                # Duplicate event already recorded, safe to skip
                pass

        # 2. Correlate events into sessions
        self.reconcile_sessions(events)
        self.conn.commit()
        return new_event_count

    def reconcile_sessions(self, recent_events: list[RawLogEvent]) -> None:
        """
        Reconcile sessions affected by recent events or full scan.
        """
        cursor = self.conn.cursor()

        # Build CID to Client Info map from recent events + database
        cid_map: dict[str, dict] = {}
        
        # Pull recent CID events
        cids_to_query = {ev.connection_id for ev in recent_events if ev.connection_id}
        if cids_to_query:
            placeholders = ",".join(["?"] * len(cids_to_query))
            cursor.execute(f"""
                SELECT connection_id, username, client_ip, client_port, virtual_hub
                FROM vpn_raw_events
                WHERE connection_id IN ({placeholders})
                ORDER BY id ASC
            """, list(cids_to_query))
            for row in cursor.fetchall():
                cid = row["connection_id"]
                if cid not in cid_map:
                    cid_map[cid] = {}
                if row["username"]:
                    cid_map[cid]["username"] = row["username"]
                if row["client_ip"]:
                    cid_map[cid]["client_ip"] = row["client_ip"]
                if row["client_port"]:
                    cid_map[cid]["client_port"] = row["client_port"]
                if row["virtual_hub"]:
                    cid_map[cid]["virtual_hub"] = row["virtual_hub"]

        # Track server restarts
        server_restarts = []
        for ev in recent_events:
            if ev.event_type == EventType.SERVER_START:
                server_restarts.append(ev.timestamp)

        # Process session creations and terminations
        for ev in recent_events:
            # Handle SESSION_CREATED
            if ev.event_type == EventType.SESSION_CREATED and ev.session_id:
                hub = ev.virtual_hub
                sess_id = ev.session_id
                username = ev.username
                client_ip = ev.client_ip
                client_port = ev.client_port

                # Enforce CID lookup if missing IP or username
                if ev.connection_id and ev.connection_id in cid_map:
                    info = cid_map[ev.connection_id]
                    username = username or info.get("username")
                    client_ip = client_ip or info.get("client_ip")
                    client_port = client_port or info.get("client_port")

                # Fallback username from session ID: SID-ALICE-1 -> alice
                if not username and sess_id.startswith("SID-"):
                    parts = sess_id.split("-")
                    if len(parts) >= 2:
                        username = parts[1]

                username = username or "unknown"

                cursor.execute("""
                    SELECT id, login_time, logout_time, status, source_logs
                    FROM vpn_sessions
                    WHERE virtual_hub = ? AND session_id = ?
                """, (hub, sess_id))
                existing = cursor.fetchone()

                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if existing:
                    # Session record exists (maybe created by earlier termination event)
                    sources = set(existing["source_logs"].split(",") if existing["source_logs"] else [])
                    sources.add(ev.source_file)
                    src_str = ",".join(filter(None, sources))

                    login_time = existing["login_time"] or ev.timestamp
                    logout_time = existing["logout_time"]
                    
                    status = existing["status"]
                    reason = None
                    duration = None
                    conf = 1.0

                    if logout_time:
                        status = SessionStatus.COMPLETED.value
                        delta = self._calc_duration(login_time, logout_time)
                        duration = delta
                    else:
                        status = SessionStatus.ACTIVE.value

                    cursor.execute("""
                        UPDATE vpn_sessions
                        SET username = COALESCE(?, username),
                            client_ip = COALESCE(?, client_ip),
                            client_port = COALESCE(?, client_port),
                            login_time = ?,
                            duration_seconds = ?,
                            status = ?,
                            status_reason = ?,
                            confidence_score = ?,
                            source_logs = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        username, client_ip, client_port, login_time,
                        duration, status, reason, conf, src_str, now_ts, existing["id"]
                    ))
                else:
                    # New session creation
                    cursor.execute("""
                        INSERT INTO vpn_sessions (
                            session_id, virtual_hub, username, client_ip,
                            client_port, login_time, logout_time, duration_seconds,
                            status, status_reason, outgoing_bytes, incoming_bytes,
                            confidence_score, source_logs, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, 0, 0, 1.0, ?, ?, ?)
                    """, (
                        sess_id, hub, username, client_ip, client_port,
                        ev.timestamp, SessionStatus.ACTIVE.value, ev.source_file,
                        now_ts, now_ts
                    ))

            # Handle SESSION_TERMINATED
            elif ev.event_type == EventType.SESSION_TERMINATED and ev.session_id:
                hub = ev.virtual_hub
                sess_id = ev.session_id
                out_bytes = ev.outgoing_bytes
                in_bytes = ev.incoming_bytes

                cursor.execute("""
                    SELECT id, username, client_ip, client_port, login_time, logout_time, status, source_logs
                    FROM vpn_sessions
                    WHERE virtual_hub = ? AND session_id = ?
                """, (hub, sess_id))
                existing = cursor.fetchone()

                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if existing:
                    sources = set(existing["source_logs"].split(",") if existing["source_logs"] else [])
                    sources.add(ev.source_file)
                    src_str = ",".join(filter(None, sources))

                    login_time = existing["login_time"]
                    logout_time = ev.timestamp

                    if login_time:
                        status = SessionStatus.COMPLETED.value
                        duration = self._calc_duration(login_time, logout_time)
                        reason = None
                        conf = 1.0
                    else:
                        status = SessionStatus.INCOMPLETE.value
                        duration = None
                        reason = "Missing login event (session began before log window)"
                        conf = 0.5

                    cursor.execute("""
                        UPDATE vpn_sessions
                        SET logout_time = ?,
                            duration_seconds = ?,
                            status = ?,
                            status_reason = ?,
                            outgoing_bytes = MAX(outgoing_bytes, ?),
                            incoming_bytes = MAX(incoming_bytes, ?),
                            confidence_score = ?,
                            source_logs = ?,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        logout_time, duration, status, reason, out_bytes,
                        in_bytes, conf, src_str, now_ts, existing["id"]
                    ))
                else:
                    # Termination without prior login found
                    username = ev.username
                    if not username and sess_id.startswith("SID-"):
                        parts = sess_id.split("-")
                        if len(parts) >= 2:
                            username = parts[1]
                    username = username or "unknown"

                    cursor.execute("""
                        INSERT INTO vpn_sessions (
                            session_id, virtual_hub, username, client_ip,
                            client_port, login_time, logout_time, duration_seconds,
                            status, status_reason, outgoing_bytes, incoming_bytes,
                            confidence_score, source_logs, created_at, updated_at
                        ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, ?, ?, ?, 0.5, ?, ?, ?)
                    """, (
                        sess_id, hub, username, ev.timestamp,
                        SessionStatus.INCOMPLETE.value,
                        "Missing login event (session began before log window)",
                        out_bytes, in_bytes, ev.source_file, now_ts, now_ts
                    ))

        # 3. Handle Server Restart Interruption
        if server_restarts:
            for r_ts in server_restarts:
                cursor.execute("""
                    SELECT id, login_time
                    FROM vpn_sessions
                    WHERE status = 'ACTIVE' AND login_time < ?
                """, (r_ts,))
                active_rows = cursor.fetchall()
                for row in active_rows:
                    duration = self._calc_duration(row["login_time"], r_ts)
                    cursor.execute("""
                        UPDATE vpn_sessions
                        SET logout_time = ?,
                            duration_seconds = ?,
                            status = 'INCOMPLETE',
                            status_reason = ?,
                            confidence_score = 0.7,
                            updated_at = ?
                        WHERE id = ?
                    """, (
                        r_ts, duration,
                        f"Terminated abnormally due to VPN Server restart at {r_ts}",
                        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        row["id"]
                    ))

    def _calc_duration(self, start_ts: str, end_ts: str) -> int:
        """Calculate duration in seconds between two timestamps."""
        try:
            t1 = start_ts.split(".")[0]
            t2 = end_ts.split(".")[0]
            dt1 = datetime.strptime(t1, "%Y-%m-%d %H:%M:%S")
            dt2 = datetime.strptime(t2, "%Y-%m-%d %H:%M:%S")
            diff = int((dt2 - dt1).total_seconds())
            return max(0, diff)
        except Exception:
            return 0
