import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import get_db

logger = logging.getLogger("uvicorn.error")


def cleanup_old_raw_events(
    retention_days: int,
    conn: Optional[sqlite3.Connection] = None,
    batch_size: int = 5000,
    now_dt: Optional[datetime] = None,
) -> int:
    """
    Safely prunes rows from vpn_raw_events older than retention_days days ago.
    Executes deletion in batches to prevent SQLite write-lock contention.
    Preserves vpn_sessions, sync_state, panel_users, and audit_logs permanently.

    Args:
        retention_days: Number of days to retain raw events. If <= 0, cleanup is disabled.
        conn: Optional existing sqlite3.Connection (useful for tests or transaction control).
        batch_size: Number of rows to delete per sub-transaction (default 5,000).
        now_dt: Optional reference datetime (defaults to UTC now).

    Returns:
        int: Number of pruned raw events.
    """
    if retention_days <= 0:
        return 0

    if now_dt is None:
        now_dt = datetime.now(timezone.utc)

    cutoff_dt = now_dt - timedelta(days=retention_days)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    def _execute_cleanup(db_conn: sqlite3.Connection) -> int:
        total_deleted = 0
        cursor = db_conn.cursor()

        while True:
            cursor.execute("""
                DELETE FROM vpn_raw_events
                WHERE id IN (
                    SELECT id FROM vpn_raw_events
                    WHERE timestamp < ?
                    LIMIT ?
                )
            """, (cutoff_str, batch_size))
            deleted = cursor.rowcount
            if deleted <= 0:
                break
            db_conn.commit()
            total_deleted += deleted
            if deleted < batch_size:
                break

        if total_deleted > 0:
            try:
                db_conn.execute("PRAGMA incremental_vacuum;")
                db_conn.execute("PRAGMA optimize;")
                db_conn.commit()
            except Exception as e:
                logger.warning(f"[Retention] Vacuum/optimize notice: {e}")

            logger.info(
                f"[Retention] Pruned {total_deleted} raw events older than {retention_days} days "
                f"(cutoff: {cutoff_str})."
            )

        return total_deleted

    if conn is not None:
        return _execute_cleanup(conn)
    else:
        with get_db() as db_conn:
            return _execute_cleanup(db_conn)
