#!/usr/bin/env python3
import sys
import getpass
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from app.config import settings
from app.database import init_db, get_db
from app.core.security import hash_password
from app.engine.synchronizer import LogSynchronizer


def create_admin():
    """Create a panel administrator from CLI."""
    init_db()
    print("=" * 55)
    print(" SoftEther VPN Log Panel - Create Administrator")
    print("=" * 55)

    username = input("Username: ").strip()
    if not username:
        print("Error: Username cannot be empty.")
        sys.exit(1)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM panel_users WHERE username = ?", (username,))
        if cursor.fetchone():
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

    password = getpass.getpass("Password (minimum 8 characters): ")
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        sys.exit(1)

    password_confirm = getpass.getpass("Confirm Password: ")
    if password != password_confirm:
        print("Error: Passwords do not match.")
        sys.exit(1)

    full_name = input("Full Name [Administrator]: ").strip() or "Administrator"

    role_input = input("Role (1: Super Administrator, 2: Administrator, 3: Viewer) [1]: ").strip()
    role_map = {"1": "superadmin", "2": "admin", "3": "viewer", "": "superadmin"}
    role = role_map.get(role_input, "superadmin")

    pwd_hash = hash_password(password)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        conn.execute("""
            INSERT INTO panel_users (username, password_hash, full_name, role, is_active, created_at)
            VALUES (?, ?, ?, ?, 1, ?)
        """, (username, pwd_hash, full_name, role, now_iso))

    print(f"\n[+] Administrator '{username}' ({role}) created successfully!")


def reset_password():
    """Reset password for an existing user from CLI."""
    init_db()
    username = input("Enter username to reset password: ").strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM panel_users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if not user:
            print(f"Error: User '{username}' not found.")
            sys.exit(1)

        password = getpass.getpass("New Password (minimum 8 characters): ")
        if len(password) < 8:
            print("Error: Password must be at least 8 characters.")
            sys.exit(1)

        confirm = getpass.getpass("Confirm New Password: ")
        if password != confirm:
            print("Error: Passwords do not match.")
            sys.exit(1)

        pwd_hash = hash_password(password)
        conn.execute("UPDATE panel_users SET password_hash = ? WHERE id = ?", (pwd_hash, user["id"]))

    print(f"\n[+] Password for '{username}' has been updated successfully.")


def sync_logs():
    """Run log synchronization from CLI."""
    init_db()
    print(f"[*] Starting log sync from: {settings.SOFTETHER_LOG_DIR.resolve()}")
    with get_db() as conn:
        sync_engine = LogSynchronizer(conn)
        stats = sync_engine.sync()

    print(f"[+] Files checked: {stats['files_checked']}")
    print(f"[+] Files updated: {stats['files_updated']}")
    print(f"[+] Events imported: {stats['events_imported']}")
    if stats["errors"]:
        print("\nWarnings / Errors:")
        for err in stats["errors"]:
            print(f" - {err}")


def test_logs():
    """Run log diagnostics from CLI."""
    init_db()
    print(f"[*] Checking SoftEther logs directory: {settings.SOFTETHER_LOG_DIR.resolve()}")
    with get_db() as conn:
        sync_engine = LogSynchronizer(conn)
        diag = sync_engine.run_diagnostics()

    print(f"Directory exists: {diag['dir_exists']}")
    print(f"Directory readable: {diag['dir_readable']}")
    print(f"Total log files found: {diag['total_files']}")
    print(f"Server log found: {diag['server_log_found']}")
    print(f"Security log found: {diag['security_log_found']}")

    if diag["warnings"]:
        print("\nDiagnostics Warnings:")
        for w in diag["warnings"]:
            print(f" [!] {w}")

    if diag["instructions"]:
        print("\nInstructions:")
        for ins in diag["instructions"]:
            print(f" [i] {ins}")


def run_server():
    """Run the FastAPI web server with uvicorn."""
    import uvicorn
    print(f"Starting SoftEther VPN Log Panel on http://{settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    )


def main():
    parser = argparse.ArgumentParser(description="SoftEther VPN Log Panel Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("create-admin", help="Create initial or new administrator")
    subparsers.add_parser("reset-password", help="Reset password for an existing user")
    subparsers.add_parser("sync-logs", help="Manually sync SoftEther logs")
    subparsers.add_parser("test-logs", help="Check log files and directory diagnostics")
    subparsers.add_parser("run", help="Start the web server")

    args = parser.parse_args()

    if args.command == "create-admin":
        create_admin()
    elif args.command == "reset-password":
        reset_password()
    elif args.command == "sync-logs":
        sync_logs()
    elif args.command == "test-logs":
        test_logs()
    elif args.command == "run":
        run_server()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
