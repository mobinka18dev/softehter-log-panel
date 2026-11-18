import math
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.api.deps import get_current_user
from app.core.jalali import parse_filter_date, gregorian_to_jalali, format_duration

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/usernames")
def get_usernames(
    query: str = Query(default="", max_length=50),
    current_user: dict = Depends(get_current_user)
):
    """Autocomplete list of distinct VPN usernames found in logs."""
    with get_db() as conn:
        cursor = conn.cursor()
        if query.strip():
            cursor.execute("""
                SELECT DISTINCT username 
                FROM vpn_sessions 
                WHERE username LIKE ? AND username != 'unknown'
                ORDER BY username ASC 
                LIMIT 30
            """, (f"%{query.strip()}%",))
        else:
            cursor.execute("""
                SELECT DISTINCT username 
                FROM vpn_sessions 
                WHERE username != 'unknown'
                ORDER BY username ASC 
                LIMIT 50
            """)
        return [row["username"] for row in cursor.fetchall()]


@router.get("/hubs")
def get_virtual_hubs(current_user: dict = Depends(get_current_user)):
    """List of distinct Virtual Hubs found in logs."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT virtual_hub FROM vpn_sessions ORDER BY virtual_hub ASC")
        return [row["virtual_hub"] for row in cursor.fetchall()]


@router.get("")
def list_sessions(
    username: str | None = Query(default=None),
    virtual_hub: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=200),
    current_user: dict = Depends(get_current_user)
):
    """
    Search and filter VPN sessions with pagination and detailed aggregate summary.
    Includes full-day coverage for end-date (up to 23:59:59).
    """
    g_from = parse_filter_date(date_from, is_end_of_day=False) if date_from else None
    g_to = parse_filter_date(date_to, is_end_of_day=True) if date_to else None

    conditions = ["1=1"]
    params: list = []

    if username and username.strip():
        conditions.append("username LIKE ?")
        params.append(f"%{username.strip()}%")

    if virtual_hub and virtual_hub.strip():
        conditions.append("virtual_hub = ?")
        params.append(virtual_hub.strip())

    if status and status.strip():
        conditions.append("status = ?")
        params.append(status.strip())

    if g_from:
        conditions.append("(login_time >= ? OR (login_time IS NULL AND logout_time >= ?))")
        params.extend([g_from, g_from])

    if g_to:
        conditions.append("(login_time <= ? OR (login_time IS NULL AND logout_time <= ?))")
        params.extend([g_to, g_to])

    where_clause = " AND ".join(conditions)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Calculate Aggregate Summary for the filtered set
        summary_query = f"""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_sessions,
                SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active_sessions,
                SUM(CASE WHEN status = 'INCOMPLETE' THEN 1 ELSE 0 END) as incomplete_sessions,
                SUM(CASE WHEN status = 'UNVERIFIED' THEN 1 ELSE 0 END) as unverified_sessions,
                SUM(CASE WHEN status = 'COMPLETED' THEN COALESCE(duration_seconds, 0) ELSE 0 END) as total_duration_seconds,
                AVG(CASE WHEN status = 'COMPLETED' THEN duration_seconds ELSE NULL END) as avg_duration_seconds,
                MAX(CASE WHEN status = 'COMPLETED' THEN duration_seconds ELSE 0 END) as max_duration_seconds,
                MIN(login_time) as first_login,
                MAX(logout_time) as last_logout
            FROM vpn_sessions
            WHERE {where_clause}
        """
        cursor.execute(summary_query, params)
        sum_row = cursor.fetchone()

        total_sessions = sum_row["total_sessions"] or 0
        total_duration = sum_row["total_duration_seconds"] or 0
        avg_duration = int(sum_row["avg_duration_seconds"] or 0)
        max_duration = sum_row["max_duration_seconds"] or 0

        summary = {
            "total_sessions": total_sessions,
            "completed_sessions": sum_row["completed_sessions"] or 0,
            "active_sessions": sum_row["active_sessions"] or 0,
            "incomplete_sessions": sum_row["incomplete_sessions"] or 0,
            "unverified_sessions": sum_row["unverified_sessions"] or 0,
            "total_duration_seconds": total_duration,
            "total_duration_formatted": format_duration(total_duration, lang="fa"),
            "avg_duration_seconds": avg_duration,
            "avg_duration_formatted": format_duration(avg_duration, lang="fa"),
            "max_duration_seconds": max_duration,
            "max_duration_formatted": format_duration(max_duration, lang="fa"),
            "first_login": sum_row["first_login"],
            "first_login_jalali": gregorian_to_jalali(sum_row["first_login"]) if sum_row["first_login"] else "-",
            "last_logout": sum_row["last_logout"],
            "last_logout_jalali": gregorian_to_jalali(sum_row["last_logout"]) if sum_row["last_logout"] else "-"
        }

        # 2. Paginated rows
        offset = (page - 1) * page_size
        data_query = f"""
            SELECT 
                id, session_id, virtual_hub, username, client_ip, client_port,
                login_time, logout_time, duration_seconds, status, status_reason,
                outgoing_bytes, incoming_bytes, confidence_score
            FROM vpn_sessions
            WHERE {where_clause}
            ORDER BY COALESCE(login_time, logout_time) DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_query, params + [page_size, offset])
        rows = cursor.fetchall()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "virtual_hub": r["virtual_hub"],
                "username": r["username"],
                "client_ip": r["client_ip"] or "-",
                "client_port": r["client_port"],
                "login_time": r["login_time"],
                "login_time_jalali": gregorian_to_jalali(r["login_time"]) if r["login_time"] else "-",
                "logout_time": r["logout_time"],
                "logout_time_jalali": gregorian_to_jalali(r["logout_time"]) if r["logout_time"] else "-",
                "duration_seconds": r["duration_seconds"],
                "duration_formatted": format_duration(r["duration_seconds"], lang="fa"),
                "status": r["status"],
                "status_reason": r["status_reason"] or "",
                "outgoing_bytes": r["outgoing_bytes"] or 0,
                "incoming_bytes": r["incoming_bytes"] or 0,
                "confidence_score": r["confidence_score"]
            })

        total_pages = math.ceil(total_sessions / page_size) if total_sessions > 0 else 1

        return {
            "items": items,
            "total_count": total_sessions,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "summary": summary
        }
