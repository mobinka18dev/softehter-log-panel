import json
from typing import Any


def get_user_vpn_scope(current_user: dict | None) -> list[str] | None:
    """
    Return normalized list of allowed VPN usernames for the current panel user.
    Returns None if user is superadmin or has unrestricted access (allowed_vpn_users is NULL or empty).
    """
    if not current_user:
        return None
    if current_user.get("role") == "superadmin":
        return None

    raw = current_user.get("allowed_vpn_users")
    if not raw:
        return None

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
    elif isinstance(raw, list):
        parsed = raw
    else:
        return None

    if not isinstance(parsed, list):
        return None

    cleaned = [str(u).strip() for u in parsed if u and str(u).strip()]
    if not cleaned:
        return None
    return cleaned


def build_scope_filter(scope: list[str] | None, column: str = "username") -> tuple[str, list[str]]:
    """
    Build SQL WHERE condition and parameters for VPN user scoping.
    If scope is None, returns ('1=1', []).
    If scope is provided, returns ('username IN (?, ...)', scope).
    """
    if not scope:
        return ("1=1", [])
    placeholders = ",".join(["?"] * len(scope))
    return (f"{column} IN ({placeholders})", list(scope))
