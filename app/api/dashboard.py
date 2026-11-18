from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.api.deps import get_current_user
from app.core.jalali import gregorian_to_jalali, format_duration

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    """Summary metrics calculated from imported VPN logs."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(DISTINCT username) as cnt FROM vpn_sessions WHERE username != 'unknown'")
        total_vpn_users = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'COMPLETED'")
        completed_sessions = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'ACTIVE'")
        active_sessions = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'INCOMPLETE'")
        incomplete_sessions = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COALESCE(SUM(duration_seconds), 0) as s FROM vpn_sessions WHERE status = 'COMPLETED'")
        total_duration = cursor.fetchone()["s"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_raw_events")
        total_events = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(DISTINCT virtual_hub) as cnt FROM vpn_sessions")
        total_hubs = cursor.fetchone()["cnt"]

        return {
            "total_vpn_users": total_vpn_users,
            "total_sessions": completed_sessions + active_sessions + incomplete_sessions,
            "completed_sessions": completed_sessions,
            "active_sessions": active_sessions,
            "incomplete_sessions": incomplete_sessions,
            "total_duration_seconds": total_duration,
            "total_duration_formatted": format_duration(total_duration, lang="fa"),
            "total_events": total_events,
            "total_hubs": total_hubs
        }


@router.get("/top-users")
def get_top_users(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Top active VPN users ranked by total connection duration."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                username,
                COUNT(*) as sessions_count,
                SUM(COALESCE(duration_seconds, 0)) as total_duration,
                MAX(login_time) as last_seen,
                MAX(client_ip) as last_ip
            FROM vpn_sessions
            WHERE username != 'unknown'
            GROUP BY username
            ORDER BY total_duration DESC, sessions_count DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

        result = []
        for r in rows:
            result.append({
                "username": r["username"],
                "sessions_count": r["sessions_count"],
                "total_duration_seconds": r["total_duration"],
                "total_duration_formatted": format_duration(r["total_duration"], lang="fa"),
                "last_seen": r["last_seen"],
                "last_seen_jalali": gregorian_to_jalali(r["last_seen"]) if r["last_seen"] else "-",
                "last_ip": r["last_ip"] or "-"
            })
        return result


@router.get("/activity-chart")
def get_activity_chart(
    days: int = Query(default=14, ge=3, le=90),
    current_user: dict = Depends(get_current_user)
):
    """Daily aggregated session counts and duration for timeline chart."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                SUBSTR(login_time, 1, 10) as day,
                COUNT(*) as session_count,
                SUM(COALESCE(duration_seconds, 0)) as duration_seconds
            FROM vpn_sessions
            WHERE login_time IS NOT NULL
            GROUP BY SUBSTR(login_time, 1, 10)
            ORDER BY day DESC
            LIMIT ?
        """, (days,))
        rows = cursor.fetchall()

        # Reverse to chronological order (oldest to newest)
        chart_data = []
        for r in reversed(rows):
            day_str = r["day"]
            chart_data.append({
                "date_gregorian": day_str,
                "date_jalali": gregorian_to_jalali(day_str, fmt="%Y/%m/%d"),
                "session_count": r["session_count"],
                "duration_seconds": r["duration_seconds"],
                "duration_hours": round(r["duration_seconds"] / 3600.0, 2)
            })
        return chart_data


@router.get("/recent-events")
def get_recent_events(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user)
):
    """Recent connection and authentication events."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                timestamp, virtual_hub, event_type, username, 
                session_id, connection_id, client_ip
            FROM vpn_raw_events
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "timestamp": r["timestamp"],
                "timestamp_jalali": gregorian_to_jalali(r["timestamp"]),
                "virtual_hub": r["virtual_hub"],
                "event_type": r["event_type"],
                "username": r["username"] or "-",
                "session_id": r["session_id"] or "-",
                "client_ip": r["client_ip"] or "-"
            })
        return result


@router.get("/quality-report")
def get_quality_report(current_user: dict = Depends(get_current_user)):
    """Parser confidence and data-quality audit report."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM vpn_sessions")
        total = cursor.fetchone()["total"]

        if total == 0:
            return {
                "overall_confidence": 100.0,
                "total_sessions": 0,
                "completed_count": 0,
                "incomplete_count": 0,
                "active_count": 0,
                "missing_logins": 0,
                "missing_logouts": 0,
                "server_restarts": 0
            }

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'COMPLETED'")
        completed = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'ACTIVE'")
        active = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status = 'INCOMPLETE'")
        incomplete = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status_reason LIKE '%Missing login%'")
        missing_logins = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM vpn_sessions WHERE status_reason LIKE '%restart%'")
        server_restarts = cursor.fetchone()["cnt"]

        cursor.execute("SELECT AVG(confidence_score) as avg_conf FROM vpn_sessions")
        avg_conf = cursor.fetchone()["avg_conf"] or 1.0

        return {
            "overall_confidence": round(avg_conf * 100, 1),
            "total_sessions": total,
            "completed_count": completed,
            "active_count": active,
            "incomplete_count": incomplete,
            "missing_logins": missing_logins,
            "missing_logouts": incomplete - missing_logins - server_restarts,
            "server_restarts": server_restarts
        }
