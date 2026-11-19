from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.api.deps import get_current_user, get_user_vpn_scope, build_scope_filter
from app.core.jalali import gregorian_to_jalali, format_duration

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    """Summary metrics calculated from imported VPN logs (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(f"SELECT COUNT(DISTINCT username) as cnt FROM vpn_sessions WHERE {scope_cond} AND username != 'unknown'", scope_params)
        total_vpn_users = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'COMPLETED'", scope_params)
        completed_sessions = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'ACTIVE'", scope_params)
        active_sessions = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'INCOMPLETE'", scope_params)
        incomplete_sessions = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'UNVERIFIED'", scope_params)
        unverified_sessions = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COALESCE(SUM(duration_seconds), 0) as s FROM vpn_sessions WHERE {scope_cond} AND status = 'COMPLETED'", scope_params)
        total_duration = cursor.fetchone()["s"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_raw_events WHERE {scope_cond}", scope_params)
        total_events = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(DISTINCT virtual_hub) as cnt FROM vpn_sessions WHERE {scope_cond}", scope_params)
        total_hubs = cursor.fetchone()["cnt"]

        return {
            "total_vpn_users": total_vpn_users,
            "total_sessions": completed_sessions + active_sessions + incomplete_sessions + unverified_sessions,
            "completed_sessions": completed_sessions,
            "active_sessions": active_sessions,
            "incomplete_sessions": incomplete_sessions,
            "unverified_sessions": unverified_sessions,
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
    """Top active VPN users ranked by total connection duration (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 
                username,
                COUNT(*) as sessions_count,
                SUM(COALESCE(duration_seconds, 0)) as total_duration,
                MAX(login_time) as last_seen,
                MAX(client_ip) as last_ip
            FROM vpn_sessions
            WHERE {scope_cond} AND username != 'unknown'
            GROUP BY username
            ORDER BY total_duration DESC, sessions_count DESC
            LIMIT ?
        """, scope_params + [limit])
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
    """Daily aggregated session counts and duration for timeline chart (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 
                SUBSTR(login_time, 1, 10) as day,
                COUNT(*) as session_count,
                SUM(COALESCE(duration_seconds, 0)) as duration_seconds
            FROM vpn_sessions
            WHERE {scope_cond} AND login_time IS NOT NULL
            GROUP BY SUBSTR(login_time, 1, 10)
            ORDER BY day DESC
            LIMIT ?
        """, scope_params + [days])
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
    """Recent connection and authentication events (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 
                timestamp, virtual_hub, event_type, username, 
                session_id, connection_id, client_ip
            FROM vpn_raw_events
            WHERE {scope_cond}
            ORDER BY id DESC
            LIMIT ?
        """, scope_params + [limit])
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
    """Parser confidence and data-quality audit report (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as total FROM vpn_sessions WHERE {scope_cond}", scope_params)
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

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'COMPLETED'", scope_params)
        completed = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'ACTIVE'", scope_params)
        active = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'INCOMPLETE'", scope_params)
        incomplete = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status = 'UNVERIFIED'", scope_params)
        unverified = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status_reason LIKE '%Missing login%'", scope_params)
        missing_logins = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT COUNT(*) as cnt FROM vpn_sessions WHERE {scope_cond} AND status_reason LIKE '%restart%'", scope_params)
        server_restarts = cursor.fetchone()["cnt"]

        cursor.execute(f"SELECT AVG(confidence_score) as avg_conf FROM vpn_sessions WHERE {scope_cond}", scope_params)
        avg_conf = cursor.fetchone()["avg_conf"] or 1.0

        return {
            "overall_confidence": round(avg_conf * 100, 1),
            "total_sessions": total,
            "completed_count": completed,
            "active_count": active,
            "incomplete_count": incomplete,
            "unverified_count": unverified,
            "missing_logins": missing_logins,
            "missing_logouts": incomplete - missing_logins - server_restarts,
            "server_restarts": server_restarts
        }


@router.get("/active-sessions")
def get_active_sessions(current_user: dict = Depends(get_current_user)):
    """Return currently active VPN sessions with real-time calculated duration (scoped to user access)."""
    scope = get_user_vpn_scope(current_user)
    scope_cond, scope_params = build_scope_filter(scope, "username")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT 
                session_id, username, virtual_hub, client_ip, client_port,
                login_time, status, status_reason, confidence_score
            FROM vpn_sessions
            WHERE {scope_cond} AND status = 'ACTIVE'
            ORDER BY login_time DESC
        """, scope_params)
        rows = cursor.fetchall()
        now_local = datetime.now()
        result = []
        for r in rows:
            duration_sec = 0
            login_time_str = r["login_time"]
            if login_time_str:
                try:
                    clean_lt = login_time_str.split(".")[0]
                    lt = datetime.strptime(clean_lt, "%Y-%m-%d %H:%M:%S")
                    diff = (now_local - lt).total_seconds()
                    duration_sec = max(0, int(diff))
                except Exception:
                    pass

            result.append({
                "session_id": r["session_id"],
                "username": r["username"],
                "virtual_hub": r["virtual_hub"],
                "client_ip": r["client_ip"] or "-",
                "client_port": r["client_port"] or "-",
                "status_reason": r["status_reason"] or "-",
                "login_time": login_time_str,
                "login_time_jalali": gregorian_to_jalali(login_time_str) if login_time_str else "-",
                "duration_seconds": duration_sec,
                "duration_formatted": format_duration(duration_sec, lang="fa"),
                "confidence_score": r["confidence_score"]
            })
        return {
            "total_active": len(result),
            "sessions": result
        }
