import os
from pathlib import Path
from datetime import datetime, timezone
import sqlite3
from app.config import settings
from app.engine.parser import parse_line, extract_hub_from_path
from app.engine.correlator import SessionCorrelator
from app.engine.models import RawLogEvent


class LogSynchronizer:
    """
    Ingests and incrementally synchronizes SoftEther VPN server and security logs.
    """

    def __init__(self, db_conn: sqlite3.Connection, log_dir: Path | None = None):
        self.conn = db_conn
        self.log_dir = log_dir or settings.SOFTETHER_LOG_DIR
        self.correlator = SessionCorrelator(db_conn)

    def discover_log_files(self) -> list[Path]:
        """
        Discover all server_log and security_log files under the configured directory.
        Returns sorted list of file paths.
        """
        if not self.log_dir.exists():
            return []

        log_files: list[Path] = []
        for root, _, files in os.walk(self.log_dir):
            for file in files:
                lower = file.lower()
                if lower.endswith(".log") or lower.endswith(".txt"):
                    p = Path(root) / file
                    log_files.append(p)

        # Sort chronologically by date in filename (YYYYMMDD), then modification time
        def _file_sort_key(p: Path) -> tuple:
            import re
            m = re.search(r"(\d{8})", p.name)
            date_part = m.group(1) if m else "99999999"
            mtime = p.stat().st_mtime if p.exists() else 0
            return (date_part, mtime, p.name)

        log_files.sort(key=_file_sort_key)
        return log_files

    def sync(self) -> dict:
        """
        Run incremental synchronization over all discovered log files.
        """
        files = self.discover_log_files()
        stats = {
            "files_checked": len(files),
            "files_updated": 0,
            "events_imported": 0,
            "errors": []
        }

        cursor = self.conn.cursor()

        for file_path in files:
            file_key = str(file_path.resolve())
            try:
                st = file_path.stat()
                file_size = st.st_size
                mtime = st.st_mtime
                file_inode = getattr(st, "st_ino", 0)
            except OSError as e:
                stats["errors"].append(f"Cannot stat {file_path.name}: {e}")
                continue

            # Query existing sync state
            cursor.execute("""
                SELECT inode, last_modified, last_byte_offset, last_line_number, events_count
                FROM sync_state
                WHERE file_path = ?
            """, (file_key,))
            state = cursor.fetchone()

            offset = 0
            line_no = 0
            prev_events = 0

            if state:
                stored_inode = state["inode"] if "inode" in state.keys() else 0
                # Inode changed (file replaced / rotated) or file truncated:
                if (stored_inode and file_inode and stored_inode != file_inode) or (file_size < state["last_byte_offset"]):
                    offset = 0
                    line_no = 0
                elif file_size == state["last_byte_offset"]:
                    # No new content
                    continue
                else:
                    offset = state["last_byte_offset"]
                    line_no = state["last_line_number"]
                    prev_events = state["events_count"]

            # Process file incrementally
            hub_name = extract_hub_from_path(file_path)
            events_batch: list[RawLogEvent] = []
            new_offset = offset
            current_line = line_no

            try:
                # Open read-only with fallback encoding
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(offset)
                    while True:
                        tell_before = f.tell()
                        line = f.readline()
                        if not line:
                            break

                        # Check if line was completely written
                        if not line.endswith("\n"):
                            # Incomplete trailing line, step back and pause here
                            f.seek(tell_before)
                            break

                        current_line += 1
                        new_offset = f.tell()

                        event = parse_line(
                            raw_line=line,
                            source_file=file_path.name,
                            line_no=current_line,
                            default_hub=hub_name
                        )
                        if event:
                            events_batch.append(event)

                        if len(events_batch) >= settings.MAX_LOG_LINE_BATCH:
                            imported = self.correlator.process_events(events_batch)
                            stats["events_imported"] += imported
                            events_batch.clear()

                    if events_batch:
                        imported = self.correlator.process_events(events_batch)
                        stats["events_imported"] += imported
                        events_batch.clear()

                stats["files_updated"] += 1
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                cursor.execute("""
                    INSERT INTO sync_state (
                        file_path, inode, last_modified, last_byte_offset,
                        last_line_number, last_synced_at, status, events_count
                    ) VALUES (?, ?, ?, ?, ?, ?, 'OK', ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        inode = excluded.inode,
                        last_modified = excluded.last_modified,
                        last_byte_offset = excluded.last_byte_offset,
                        last_line_number = excluded.last_line_number,
                        last_synced_at = excluded.last_synced_at,
                        status = 'OK',
                        events_count = events_count + ?
                """, (
                    file_key, file_inode, mtime, new_offset, current_line, now_str,
                    stats["events_imported"], stats["events_imported"]
                ))
                self.conn.commit()

            except Exception as e:
                stats["errors"].append(f"Error reading {file_path.name}: {e}")
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    INSERT INTO sync_state (
                        file_path, inode, last_modified, last_byte_offset,
                        last_line_number, last_synced_at, status, events_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(file_path) DO UPDATE SET
                        inode = excluded.inode,
                        status = excluded.status,
                        last_synced_at = excluded.last_synced_at
                """, (file_key, file_inode, mtime, offset, line_no, now_str, f"ERROR: {e}", prev_events))
                self.conn.commit()

        return stats

    def run_diagnostics(self) -> dict:
        """
        Run diagnostics on the configured log directory and return status & recommendations.
        """
        diag = {
            "configured_dir": str(self.log_dir.resolve()),
            "dir_exists": self.log_dir.exists(),
            "dir_readable": False,
            "server_log_found": False,
            "security_log_found": False,
            "total_files": 0,
            "warnings": [],
            "instructions": []
        }

        if not self.log_dir.exists():
            diag["warnings"].append(
                f"Log directory '{self.log_dir}' does not exist. Please check SOFTETHER_LOG_DIR configuration."
            )
            diag["instructions"].append(
                "Ensure SoftEther log path is mounted or accessible. On Ubuntu, default path is usually /var/log/vpnserver or /usr/local/vpnserver."
            )
            return diag

        try:
            # Check read permission
            os.listdir(self.log_dir)
            diag["dir_readable"] = True
        except PermissionError:
            diag["warnings"].append(f"No read permission for directory '{self.log_dir}'.")
            diag["instructions"].append(
                "Grant read-only permission using POSIX ACL: sudo setfacl -R -m u:softether-panel:rX /path/to/logs"
            )
            return diag

        files = self.discover_log_files()
        diag["total_files"] = len(files)

        for f in files:
            p_str = str(f).lower()
            if "server_log" in p_str or "vpn_" in f.name.lower():
                diag["server_log_found"] = True
            if "security_log" in p_str or "sec_" in f.name.lower():
                diag["security_log_found"] = True

        if not diag["server_log_found"]:
            diag["warnings"].append("No server_log files found.")
            diag["instructions"].append(
                "In SoftEther VPN Server Manager, verify Server Log is enabled (Management -> Server Log Setting)."
            )

        if not diag["security_log_found"]:
            diag["warnings"].append("No security_log files found.")
            diag["instructions"].append(
                "In SoftEther VPN Server Manager, ensure Security Log is enabled for each Virtual Hub (Hub Administration -> Log Setting)."
            )

        return diag
