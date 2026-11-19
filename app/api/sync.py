from fastapi import APIRouter, Depends
from app.database import get_db
from app.api.deps import require_role, record_audit
from app.engine.synchronizer import LogSynchronizer

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/run")
def trigger_sync(current_user: dict = Depends(require_role(["superadmin", "admin"]))):
    """Trigger manual incremental synchronization of SoftEther logs."""
    with get_db() as conn:
        sync_engine = LogSynchronizer(conn)
        stats = sync_engine.sync()

    record_audit(
        action="SYNC_MANUAL_TRIGGER",
        details=f"Ran log sync. Files checked: {stats['files_checked']}, imported: {stats['events_imported']}",
        user=current_user
    )

    return stats


@router.get("/status")
def get_sync_status(current_user: dict = Depends(require_role(["superadmin", "admin"]))):
    """Get last synchronization status and tracked log files."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, file_path, last_byte_offset, last_line_number, 
                   last_synced_at, status, events_count
            FROM sync_state
            ORDER BY last_synced_at DESC
        """)
        files = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
        total_raw = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions")
        total_sessions = cursor.fetchone()["cnt"]

        return {
            "tracked_files": files,
            "total_raw_events": total_raw,
            "total_sessions": total_sessions
        }


@router.get("/diagnostics")
def get_sync_diagnostics(current_user: dict = Depends(require_role(["superadmin", "admin"]))):
    """Run diagnostics on SoftEther log paths and logging settings."""
    with get_db() as conn:
        sync_engine = LogSynchronizer(conn)
        diag = sync_engine.run_diagnostics()
        return diag
