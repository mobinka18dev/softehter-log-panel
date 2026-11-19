import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.database import get_db
from app.api.deps import require_role, record_audit, get_current_user
from app.core.security import hash_password

router = APIRouter(prefix="/api/panel-users", tags=["panel-users"])


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: str | None = Field(default="", max_length=100)
    role: str = Field(..., pattern="^(superadmin|admin|viewer)$")
    allowed_vpn_users: list[str] | None = None


class UpdateUserRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, pattern="^(superadmin|admin|viewer)$")
    is_active: bool | None = None
    allowed_vpn_users: list[str] | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=8)


@router.get("")
def list_panel_users(
    current_user: dict = Depends(require_role(["superadmin", "admin"]))
):
    """List all application panel users (excluding password hashes)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, full_name, role, is_active, created_at, last_login_at, allowed_vpn_users
            FROM panel_users
            ORDER BY id ASC
        """)
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            if d.get("allowed_vpn_users"):
                try:
                    d["allowed_vpn_users"] = json.loads(d["allowed_vpn_users"]) if isinstance(d["allowed_vpn_users"], str) else d["allowed_vpn_users"]
                except Exception:
                    d["allowed_vpn_users"] = None
            else:
                d["allowed_vpn_users"] = None
            rows.append(d)
        return rows


@router.post("")
def create_panel_user(
    req: CreateUserRequest,
    current_user: dict = Depends(require_role(["superadmin"]))
):
    """Create a new panel user (Superadmin only)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM panel_users WHERE username = ?", (req.username.strip(),))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Username '{req.username}' already exists."
            )

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        pwd_hash = hash_password(req.password)

        allowed_val = None
        if req.allowed_vpn_users:
            cleaned = [str(u).strip() for u in req.allowed_vpn_users if str(u).strip()]
            if cleaned:
                allowed_val = json.dumps(cleaned)

        cursor.execute("""
            INSERT INTO panel_users (
                username, password_hash, full_name, role, is_active, created_at, allowed_vpn_users
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (req.username.strip(), pwd_hash, req.full_name or "", req.role, now_iso, allowed_val))
        new_id = cursor.lastrowid

    record_audit(
        action="USER_CREATE",
        details=f"Created panel user '{req.username}' with role '{req.role}'",
        user=current_user
    )

    return {"message": "User created successfully", "id": new_id, "username": req.username}


@router.put("/{user_id}")
def update_panel_user(
    user_id: int,
    req: UpdateUserRequest,
    current_user: dict = Depends(require_role(["superadmin"]))
):
    """Update user attributes (role, active state, name, allowed VPN users)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role, is_active FROM panel_users WHERE id = ?", (user_id,))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Prevent disabling own superadmin account
        if user_id == current_user["id"] and req.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot disable your own administrator account."
            )

        updates = []
        params = []
        if req.full_name is not None:
            updates.append("full_name = ?")
            params.append(req.full_name)
        if req.role is not None:
            updates.append("role = ?")
            params.append(req.role)
        if req.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if req.is_active else 0)
        if "allowed_vpn_users" in req.model_fields_set:
            allowed_val = None
            if req.allowed_vpn_users:
                cleaned = [str(u).strip() for u in req.allowed_vpn_users if str(u).strip()]
                if cleaned:
                    allowed_val = json.dumps(cleaned)
            updates.append("allowed_vpn_users = ?")
            params.append(allowed_val)

        if updates:
            params.append(user_id)
            query = f"UPDATE panel_users SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

    record_audit(
        action="USER_UPDATE",
        details=f"Updated panel user id {user_id} ({target['username']})",
        user=current_user
    )

    return {"message": "User updated successfully"}


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    req: ResetPasswordRequest,
    current_user: dict = Depends(get_current_user)
):
    """Reset user password. Superadmin can reset any password; users can reset their own."""
    is_self = (current_user["id"] == user_id)
    is_superadmin = (current_user["role"] == "superadmin")

    if not is_self and not is_superadmin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to reset this user's password."
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM panel_users WHERE id = ?", (user_id,))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        pwd_hash = hash_password(req.new_password)
        cursor.execute("UPDATE panel_users SET password_hash = ? WHERE id = ?", (pwd_hash, user_id))

    record_audit(
        action="USER_PASSWORD_RESET",
        details=f"Reset password for user '{target['username']}'",
        user=current_user
    )

    return {"message": "Password reset successfully"}


@router.delete("/{user_id}")
def delete_panel_user(
    user_id: int,
    current_user: dict = Depends(require_role(["superadmin"]))
):
    """Delete a panel user account."""
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account."
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM panel_users WHERE id = ?", (user_id,))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        cursor.execute("DELETE FROM panel_users WHERE id = ?", (user_id,))

    record_audit(
        action="USER_DELETE",
        details=f"Deleted panel user '{target['username']}'",
        user=current_user
    )

    return {"message": f"User '{target['username']}' deleted successfully"}
