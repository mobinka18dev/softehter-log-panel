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
                SELECT connection_id, username, client_ip, client_port, virtual_hub, event_type
                FROM vpn_raw_events
                WHERE connection_id IN ({placeholders})
                ORDER BY id ASC
            """, list(cids_to_query))
            for row in cursor.fetchall():
                cid = row["connection_id"]
                if cid not in cid_map:
                    cid_map[cid] = {}
                if row["username"] and (row["event_type"] == EventType.AUTH_SUCCESS.value or not cid_map[cid].get("username")):
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

                # Enforce CID lookup for authenticated username, IP, port
                if ev.connection_id and ev.connection_id in cid_map:
                    info = cid_map[ev.connection_id]
                    if info.get("username"):
                        username = info["username"]
                    else:
                        username = username or info.get("username")
                    client_ip = client_ip or info.get("client_ip")
                    client_port = client_port or info.get("client_port")

                # Fallback username from session ID: SID-ALICE-1 -> ALICE
                if not username and sess_id.startswith("SID-"):
                    parts = sess_id.split("-")
                    if len(parts) >= 2:
                        username = parts[1]

                username = username or "unknown"

                # Check if this exact login instance was already recorded (e.g. in both server_log and security_log)
                # or if an orphaned termination event arrived first
                cursor.execute("""
                    SELECT id, virtual_hub, login_time, logout_time, status, source_logs
                    FROM vpn_sessions
                    WHERE (session_id = ? AND (login_time = ? OR login_time IS NULL))
                       OR (virtual_hub = ? AND session_id = ? AND login_time = ?)
                    ORDER BY id DESC LIMIT 1
                """, (sess_id, ev.timestamp, hub, sess_id, ev.timestamp))
                existing = cursor.fetchone()

                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if existing:
                    sources = set(existing["source_logs"].split(",") if existing["source_logs"] else [])
                    sources.add(ev.source_file)
                    src_str = ",".join(filter(None, sources))

                    login_time = existing["login_time"] or ev.timestamp
                    logout_time = existing["logout_time"]

                    if logout_time:
                        status = SessionStatus.COMPLETED.value
                        delta = self._calc_duration(login_time, logout_time)
                        duration = delta
                        reason = None
                        conf = 1.0
                    else:
                        status = SessionStatus.ACTIVE.value
                        duration = None
                        reason = None
                        conf = 1.0

                    target_hub = hub if hub != 'DEFAULT' else existing["virtual_hub"]
                    try:
                        cursor.execute("""
                            UPDATE vpn_sessions
                            SET username = CASE WHEN ? != 'unknown' THEN ? ELSE username END,
                                virtual_hub = ?,
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
                            username, username, target_hub, client_ip, client_port, login_time,
                            duration, status, reason, conf, src_str, now_ts, existing["id"]
                        ))
                    except sqlite3.IntegrityError:
                        pass
                else:
                    # Brand new session creation: immediately mark as ACTIVE with safe ON CONFLICT merge
                    try:
                        cursor.execute("""
                            INSERT INTO vpn_sessions (
                                session_id, virtual_hub, username, client_ip,
                                client_port, login_time, logout_time, duration_seconds,
                                status, status_reason, outgoing_bytes, incoming_bytes,
                                confidence_score, source_logs, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, 0, 0, 1.0, ?, ?, ?)
                            ON CONFLICT(virtual_hub, session_id, login_time) DO UPDATE SET
                                username = CASE WHEN excluded.username != 'unknown' THEN excluded.username ELSE vpn_sessions.username END,
                                client_ip = COALESCE(excluded.client_ip, vpn_sessions.client_ip),
                                client_port = COALESCE(excluded.client_port, vpn_sessions.client_port),
                                source_logs = vpn_sessions.source_logs || ',' || excluded.source_logs,
                                updated_at = excluded.updated_at
                        """, (
                            sess_id, hub, username, client_ip, client_port,
                            ev.timestamp, SessionStatus.ACTIVE.value, ev.source_file,
                            now_ts, now_ts
                        ))
                    except sqlite3.IntegrityError:
                        pass

            # Handle SESSION_TERMINATED
            elif ev.event_type == EventType.SESSION_TERMINATED and ev.session_id:
                hub = ev.virtual_hub
                sess_id = ev.session_id
                out_bytes = ev.outgoing_bytes
                in_bytes = ev.incoming_bytes

                # Match the open ACTIVE session first (or previously marked UNVERIFIED)
                cursor.execute("""
                    SELECT id, virtual_hub, username, client_ip, client_port, login_time, logout_time, status, source_logs
                    FROM vpn_sessions
                    WHERE session_id = ? AND status IN ('ACTIVE', 'UNVERIFIED')
                    ORDER BY id DESC LIMIT 1
                """, (sess_id,))
                existing = cursor.fetchone()

                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if existing:
                    sources = set(existing["source_logs"].split(",") if existing["source_logs"] else [])
                    sources.add(ev.source_file)
                    src_str = ",".join(filter(None, sources))

                    login_time = existing["login_time"]
                    logout_time = ev.timestamp
                    duration = self._calc_duration(login_time, logout_time) if login_time else None

                    target_hub = hub if hub != 'DEFAULT' else existing["virtual_hub"]
                    try:
                        cursor.execute("""
                            UPDATE vpn_sessions
                            SET virtual_hub = ?,
                                logout_time = ?,
                                duration_seconds = ?,
                                status = 'COMPLETED',
                                status_reason = NULL,
                                outgoing_bytes = MAX(outgoing_bytes, ?),
                                incoming_bytes = MAX(incoming_bytes, ?),
                                confidence_score = 1.0,
                                source_logs = ?,
                                updated_at = ?
                            WHERE id = ?
                        """, (
                            target_hub, logout_time, duration, out_bytes,
                            in_bytes, src_str, now_ts, existing["id"]
                        ))
                    except sqlite3.IntegrityError:
                        pass
                else:
                    # Check if this termination was already recorded (e.g. duplicate event from both logs)
                    cursor.execute("""
                        SELECT id, source_logs, virtual_hub
                        FROM vpn_sessions
                        WHERE (session_id = ? AND logout_time = ?)
                           OR (virtual_hub = ? AND session_id = ? AND logout_time = ?)
                        ORDER BY id DESC LIMIT 1
                    """, (sess_id, ev.timestamp, hub, sess_id, ev.timestamp))
                    dup_term = cursor.fetchone()
                    if dup_term:
                        sources = set(dup_term["source_logs"].split(",") if dup_term["source_logs"] else [])
                        sources.add(ev.source_file)
                        src_str = ",".join(filter(None, sources))
                        target_hub = hub if hub != 'DEFAULT' else dup_term["virtual_hub"]
                        try:
                            cursor.execute("""
                                UPDATE vpn_sessions
                                SET virtual_hub = ?,
                                    outgoing_bytes = MAX(outgoing_bytes, ?),
                                    incoming_bytes = MAX(incoming_bytes, ?),
                                    source_logs = ?,
                                    updated_at = ?
                                WHERE id = ?
                            """, (target_hub, out_bytes, in_bytes, src_str, now_ts, dup_term["id"]))
                        except sqlite3.IntegrityError:
                            pass
                    else:
                        # Termination without prior login found
                        username = ev.username
                        if not username and sess_id.startswith("SID-"):
                            parts = sess_id.split("-")
                            if len(parts) >= 2:
                                username = parts[1]
                        username = username or "unknown"

                        try:
                            cursor.execute("""
                                INSERT INTO vpn_sessions (
                                    session_id, virtual_hub, username, client_ip,
                                    client_port, login_time, logout_time, duration_seconds,
                                    status, status_reason, outgoing_bytes, incoming_bytes,
                                    confidence_score, source_logs, created_at, updated_at
                                ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, ?, ?, ?, 0.5, ?, ?, ?)
                                ON CONFLICT(virtual_hub, session_id, login_time) DO UPDATE SET
                                    outgoing_bytes = MAX(vpn_sessions.outgoing_bytes, excluded.outgoing_bytes),
                                    incoming_bytes = MAX(vpn_sessions.incoming_bytes, excluded.incoming_bytes),
                                    source_logs = vpn_sessions.source_logs || ',' || excluded.source_logs,
                                    updated_at = excluded.updated_at
                            """, (
                                sess_id, hub, username, ev.timestamp,
                                SessionStatus.INCOMPLETE.value,
                                "Missing login event (session began before log window)",
                                out_bytes, in_bytes, ev.source_file, now_ts, now_ts
                            ))
                        except sqlite3.IntegrityError:
                            pass

            # Handle AUTH_SUCCESS: update any sessions with unknown username
            elif ev.event_type == EventType.AUTH_SUCCESS and ev.username:
                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if ev.connection_id:
                    cursor.execute("""
                        SELECT session_id FROM vpn_raw_events
                        WHERE connection_id = ? AND session_id IS NOT NULL
                    """, (ev.connection_id,))
                    sids = [r["session_id"] for r in cursor.fetchall()]
                    for sid in sids:
                        cursor.execute("""
                            UPDATE vpn_sessions
                            SET username = ?, updated_at = ?
                            WHERE session_id = ? AND (username = 'unknown' OR username IS NULL)
                        """, (ev.username, now_ts, sid))

            # Handle CONN_CREATED with session_id (e.g. from VPN Client details)
            elif ev.event_type == EventType.CONN_CREATED and ev.session_id:
                sess_id = ev.session_id
                now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    UPDATE vpn_sessions
                    SET client_ip = COALESCE(?, client_ip),
                        client_port = COALESCE(?, client_port),
                        virtual_hub = CASE WHEN (virtual_hub = 'DEFAULT' OR virtual_hub IS NULL) AND ? != 'DEFAULT' THEN ? ELSE virtual_hub END,
                        updated_at = ?
                    WHERE session_id = ?
                """, (ev.client_ip, ev.client_port, ev.virtual_hub, ev.virtual_hub, now_ts, sess_id))

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

        # 4. Handle Old Sessions Without Logout (Mark as UNVERIFIED when subsequent logs exceed observation threshold)
        # Note: A session lasting 72 hours (3 days) or more is legitimately ACTIVE during normal operation.
        # If subsequent logs arrive from much later dates (> 7 days) without any logout or server restart event,
        # its status cannot be confirmed from available logs and is explicitly marked UNVERIFIED (never fabricating logout time).
        if recent_events:
            valid_timestamps = [ev.timestamp for ev in recent_events if ev.timestamp]
            if valid_timestamps:
                latest_ev_ts = max(valid_timestamps)
                cursor.execute("SELECT id, login_time FROM vpn_sessions WHERE status = 'ACTIVE' AND login_time IS NOT NULL")
                for row in cursor.fetchall():
                    delta = self._calc_duration(row["login_time"], latest_ev_ts)
                    if delta > (7 * 86400):  # More than 7 days without a logout event in subsequent logs
                        cursor.execute("""
                            UPDATE vpn_sessions
                            SET status = 'UNVERIFIED',
                                status_reason = 'No logout event recorded in log stream; session status cannot be verified from available records',
                                confidence_score = 0.5,
                                updated_at = ?
                            WHERE id = ?
                        """, (
                            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                            row["id"]
                        ))

    def mark_unverified(self, session_id: str, reason: str = "No logout event recorded in log stream; session status cannot be verified from available records") -> None:
        """Explicitly mark a session as UNVERIFIED without inventing logout timestamps."""
        cursor = self.conn.cursor()
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE vpn_sessions
            SET status = 'UNVERIFIED',
                status_reason = ?,
                confidence_score = 0.5,
                updated_at = ?
            WHERE session_id = ? AND status = 'ACTIVE'
        """, (reason, now_ts, session_id))
        self.conn.commit()

    def correlate_all(self) -> dict:
        """
        Reconcile all sessions in the database:
        1. Find any active sessions that have matching termination events in vpn_raw_events.
        2. Resolve usernames for any unknown sessions.
        3. Check server restart interruptions.
        4. Check stale sessions (> 7 days) and mark UNVERIFIED.
        Returns metrics summary.
        """
        cursor = self.conn.cursor()
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        updated_count = 0

        # 1. Close any ACTIVE or UNVERIFIED sessions if a termination event exists
        cursor.execute("SELECT id, session_id, login_time, outgoing_bytes, incoming_bytes FROM vpn_sessions WHERE status IN ('ACTIVE', 'UNVERIFIED')")
        active_sessions = cursor.fetchall()
        for sess in active_sessions:
            sess_id = sess["session_id"]
            login_ts = sess["login_time"]
            cursor.execute("""
                SELECT timestamp, outgoing_bytes, incoming_bytes
                FROM vpn_raw_events
                WHERE session_id = ? AND event_type = ? AND timestamp >= ?
                ORDER BY timestamp ASC LIMIT 1
            """, (sess_id, EventType.SESSION_TERMINATED.value, login_ts or ""))
            term_ev = cursor.fetchone()
            if term_ev:
                logout_ts = term_ev["timestamp"]
                dur = self._calc_duration(login_ts, logout_ts) if login_ts else 0
                out_b = max(sess["outgoing_bytes"] or 0, term_ev["outgoing_bytes"] or 0)
                in_b = max(sess["incoming_bytes"] or 0, term_ev["incoming_bytes"] or 0)
                cursor.execute("""
                    UPDATE vpn_sessions
                    SET logout_time = ?,
                        duration_seconds = ?,
                        status = 'COMPLETED',
                        status_reason = NULL,
                        outgoing_bytes = ?,
                        incoming_bytes = ?,
                        confidence_score = 1.0,
                        updated_at = ?
                    WHERE id = ?
                """, (logout_ts, dur, out_b, in_b, now_ts, sess["id"]))
                updated_count += 1

        # 2. Check for server restarts interrupting ACTIVE sessions
        cursor.execute("""
            SELECT timestamp FROM vpn_raw_events
            WHERE event_type = ?
            ORDER BY timestamp ASC
        """, (EventType.SERVER_START.value,))
        for row in cursor.fetchall():
            r_ts = row["timestamp"]
            cursor.execute("""
                SELECT id, login_time FROM vpn_sessions
                WHERE status = 'ACTIVE' AND login_time < ?
            """, (r_ts,))
            for r in cursor.fetchall():
                dur = self._calc_duration(r["login_time"], r_ts)
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
                    r_ts, dur,
                    f"Terminated abnormally due to VPN Server restart at {r_ts}",
                    now_ts, r["id"]
                ))
                updated_count += 1

        # 3. Check for stale sessions (> 7 days) without termination compared to latest log stream event
        cursor.execute("SELECT MAX(timestamp) as latest_ts FROM vpn_raw_events")
        max_row = cursor.fetchone()
        ref_ts = max_row["latest_ts"] if (max_row and max_row["latest_ts"]) else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("SELECT id, login_time FROM vpn_sessions WHERE status = 'ACTIVE' AND login_time IS NOT NULL")
        for r in cursor.fetchall():
            delta = self._calc_duration(r["login_time"], ref_ts)
            if delta > (7 * 86400):
                cursor.execute("""
                    UPDATE vpn_sessions
                    SET status = 'UNVERIFIED',
                        status_reason = 'No logout event recorded in log stream; session status cannot be verified from available records',
                        confidence_score = 0.5,
                        updated_at = ?
                    WHERE id = ?
                """, (now_ts, r["id"]))
                updated_count += 1

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'ACTIVE'")
        active_count = cursor.fetchone()["cnt"]

        self.conn.commit()
        return {
            "sessions_updated": updated_count,
            "active_sessions": active_count
        }

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
