import math
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.api.deps import require_role
from app.core.jalali import gregorian_to_jalali

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=5, le=100),
    current_user: dict = Depends(require_role(["superadmin", "admin"]))
):
    """List administrative audit logs with pagination."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM audit_logs")
        total = cursor.fetchone()["cnt"]

        offset = (page - 1) * page_size
        cursor.execute("""
            SELECT id, user_id, username, action, details, ip_address, created_at
            FROM audit_logs
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """, (page_size, offset))
        rows = cursor.fetchall()

        items = []
        for r in rows:
            items.append({
                "id": r["id"],
                "user_id": r["user_id"],
                "username": r["username"],
                "action": r["action"],
                "details": r["details"],
                "ip_address": r["ip_address"] or "-",
                "created_at": r["created_at"],
                "created_at_jalali": gregorian_to_jalali(r["created_at"])
            })

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return {
            "items": items,
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
