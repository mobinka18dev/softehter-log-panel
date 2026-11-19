from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel, Field
from app.database import get_db
from app.core.security import verify_password, hash_password, create_access_token
from app.core.rate_limiter import is_rate_limited, record_failed_attempt, clear_rate_limit
from app.api.deps import get_current_user, get_current_user_optional, record_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4)


class InitialSetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: str | None = Field(default="Administrator", max_length=100)


@router.get("/setup-status")
def check_setup_status():
    """Check if the system requires first-time administrator initialization."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM panel_users")
        count = cursor.fetchone()["cnt"]
        return {"setup_needed": count == 0}


@router.post("/initial-setup")
def initial_setup(req: InitialSetupRequest, request: Request):
    """
    First-run setup wizard. Creates the initial Super Administrator.
    Locked immediately once any user exists.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM panel_users")
        if cursor.fetchone()["cnt"] > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Initial setup has already been completed. Contact an existing Super Admin."
            )

        # Enforce password strength
        if len(req.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long."
            )

        pwd_hash = hash_password(req.password)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO panel_users (
                username, password_hash, full_name, role, is_active, created_at
            ) VALUES (?, ?, ?, 'superadmin', 1, ?)
        """, (req.username.strip(), pwd_hash, req.full_name.strip() if req.full_name else "", now_iso))
        user_id = cursor.lastrowid

    record_audit(
        action="INITIAL_SETUP",
        details=f"Created initial Super Administrator '{req.username}'",
        user={"id": user_id, "username": req.username},
        ip_address=client_ip
    )

    return {"message": "Administrator initialized successfully. You may now log in."}


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    """Authenticate panel user with rate limiting."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_key = f"{client_ip}:{req.username}"

    # Check rate limiting
    limited, retry_after = is_rate_limited(rate_key)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please try again in {retry_after} seconds."
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, password_hash, full_name, role, is_active, allowed_vpn_users
            FROM panel_users
            WHERE username = ?
        """, (req.username.strip(),))
        user = cursor.fetchone()

        if not user or not verify_password(req.password, user["password_hash"]):
            record_failed_attempt(rate_key)
            record_audit(
                action="LOGIN_FAILED",
                details=f"Failed login attempt for username '{req.username}'",
                ip_address=client_ip
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )

        if user["is_active"] != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled. Contact system administrator."
            )

        # Clear rate limit and update last login
        clear_rate_limit(rate_key)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE panel_users
            SET last_login_at = ?, failed_login_attempts = 0
            WHERE id = ?
        """, (now_iso, user["id"]))

    # Create JWT
    token_payload = {
        "sub": user["username"],
        "role": user["role"],
        "id": user["id"]
    }
    access_token = create_access_token(token_payload)

    # Set session cookie (no max_age so it expires when browser is closed)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=False  # Set to True if using HTTPS
    )

    record_audit(
        action="LOGIN_SUCCESS",
        details=f"User '{user['username']}' logged in successfully",
        user=dict(user),
        ip_address=client_ip
    )

    import json
    allowed = None
    if user["allowed_vpn_users"]:
        try:
            allowed = json.loads(user["allowed_vpn_users"]) if isinstance(user["allowed_vpn_users"], str) else user["allowed_vpn_users"]
        except Exception:
            allowed = None

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "allowed_vpn_users": allowed
        }
    }


@router.api_route("/logout", methods=["GET", "POST"])
def logout(response: Response, current_user: dict | None = Depends(get_current_user_optional)):
    """Log out current user and clear auth cookie."""
    response.delete_cookie("access_token")
    if current_user:
        record_audit(
            action="LOGOUT",
            details=f"User '{current_user['username']}' logged out",
            user=current_user
        )
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return currently authenticated user profile."""
    import json
    allowed = None
    if current_user.get("allowed_vpn_users"):
        try:
            allowed = json.loads(current_user["allowed_vpn_users"]) if isinstance(current_user["allowed_vpn_users"], str) else current_user["allowed_vpn_users"]
        except Exception:
            allowed = None
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "full_name": current_user["full_name"],
        "role": current_user["role"],
        "allowed_vpn_users": allowed,
        "last_login_at": current_user.get("last_login_at")
    }
