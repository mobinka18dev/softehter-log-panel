from typing import Annotated
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
import sqlite3
from app.config import settings
from app.database import get_db
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user_optional(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None
) -> dict | None:
    """Extract and validate current user from Authorization header or Cookie."""
    # Check Authorization header first, then cookie
    auth_token = token
    if not auth_token:
        auth_token = request.cookies.get("access_token")
    
    if not auth_token:
        return None

    payload = decode_access_token(auth_token)
    if not payload:
        return None

    username = payload.get("sub")
    if not username:
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, full_name, role, is_active, last_login_at
            FROM panel_users
            WHERE username = ?
        """, (username,))
        row = cursor.fetchone()
        if not row or row["is_active"] != 1:
            return None
        return dict(row)


def get_current_user(
    current_user: Annotated[dict | None, Depends(get_current_user_optional)]
) -> dict:
    """Enforce authentication."""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


def require_role(allowed_roles: list[str]):
    """Role-based access control dependency."""
    def role_checker(user: Annotated[dict, Depends(get_current_user)]) -> dict:
        user_role = user.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}"
            )
        return user
    return role_checker


def record_audit(
    action: str,
    details: str,
    user: dict | None = None,
    ip_address: str | None = None
) -> None:
    """Record an administrative action to audit_logs."""
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    user_id = user["id"] if user else None
    username = user["username"] if user else "anonymous"

    with get_db() as conn:
        conn.execute("""
            INSERT INTO audit_logs (user_id, username, action, details, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, details, ip_address, now_iso))
