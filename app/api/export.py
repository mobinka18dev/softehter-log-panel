from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Response
from app.database import get_db
from app.api.deps import get_current_user, record_audit, get_user_vpn_scope, build_scope_filter
from app.core.jalali import parse_filter_date, gregorian_to_jalali, format_duration
from app.reports.excel import generate_excel_report
from app.reports.csv_export import generate_csv_report

router = APIRouter(prefix="/api/export", tags=["export"])


def _fetch_filtered_data(
    username: str | None = None,
    virtual_hub: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    scope: list[str] | None = None
) -> tuple[list[dict], dict]:
    """Helper to fetch exact filtered rows and summary for exports, strictly scoped."""
    g_from = parse_filter_date(date_from, is_end_of_day=False) if date_from else None
    g_to = parse_filter_date(date_to, is_end_of_day=True) if date_to else None

    conditions = ["1=1"]
    params: list = []

    if scope:
        scope_cond, scope_params = build_scope_filter(scope, "username")
        conditions.append(scope_cond)
        params.extend(scope_params)

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

        # Summary query
        summary_query = f"""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_sessions,
                SUM(CASE WHEN status = 'ACTIVE' THEN 1 ELSE 0 END) as active_sessions,
                SUM(CASE WHEN status = 'INCOMPLETE' THEN 1 ELSE 0 END) as incomplete_sessions,
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

        summary = {
            "total_sessions": sum_row["total_sessions"] or 0,
            "completed_sessions": sum_row["completed_sessions"] or 0,
            "active_sessions": sum_row["active_sessions"] or 0,
            "incomplete_sessions": sum_row["incomplete_sessions"] or 0,
            "total_duration_seconds": sum_row["total_duration_seconds"] or 0,
            "avg_duration_seconds": int(sum_row["avg_duration_seconds"] or 0),
            "max_duration_seconds": sum_row["max_duration_seconds"] or 0,
            "first_login": sum_row["first_login"],
            "last_logout": sum_row["last_logout"]
        }

        # Data query (limit to 50,000 for export safety)
        data_query = f"""
            SELECT 
                id, session_id, virtual_hub, username, client_ip, client_port,
                login_time, logout_time, duration_seconds, status, status_reason,
                outgoing_bytes, incoming_bytes
            FROM vpn_sessions
            WHERE {where_clause}
            ORDER BY COALESCE(login_time, logout_time) DESC
            LIMIT 50000
        """
        cursor.execute(data_query, params)
        rows = [dict(r) for r in cursor.fetchall()]

    return rows, summary


@router.get("/excel")
def export_excel(
    username: str | None = Query(default=None),
    virtual_hub: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    lang: str = Query(default="fa"),
    current_user: dict = Depends(get_current_user)
):
    """Export filtered VPN session report to professional Excel spreadsheet (strictly scoped)."""
    scope = get_user_vpn_scope(current_user)
    rows, summary = _fetch_filtered_data(
        username=username,
        virtual_hub=virtual_hub,
        status=status,
        date_from=date_from,
        date_to=date_to,
        scope=scope
    )

    excel_bytes = generate_excel_report(
        sessions=rows,
        summary=summary,
        filter_username=username,
        filter_hub=virtual_hub,
        date_from=date_from,
        date_to=date_to,
        lang=lang
    )

    now_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"vpn_report_{now_tag}.xlsx"

    record_audit(
        action="EXPORT_EXCEL",
        details=f"Exported {len(rows)} sessions to Excel (filters: user={username}, hub={virtual_hub})",
        user=current_user
    )

    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.get("/csv")
def export_csv(
    username: str | None = Query(default=None),
    virtual_hub: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    lang: str = Query(default="fa"),
    current_user: dict = Depends(get_current_user)
):
    """Export filtered VPN session report to Excel-compatible CSV (UTF-8 BOM, strictly scoped)."""
    scope = get_user_vpn_scope(current_user)
    rows, _ = _fetch_filtered_data(
        username=username,
        virtual_hub=virtual_hub,
        status=status,
        date_from=date_from,
        date_to=date_to,
        scope=scope
    )

    csv_bytes = generate_csv_report(sessions=rows, lang=lang)
    now_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"vpn_report_{now_tag}.csv"

    record_audit(
        action="EXPORT_CSV",
        details=f"Exported {len(rows)} sessions to CSV (filters: user={username}, hub={virtual_hub})",
        user=current_user
    )

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
