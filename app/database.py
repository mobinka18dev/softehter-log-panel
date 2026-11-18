import sqlite3
from contextlib import contextmanager
from typing import Generator
from pathlib import Path
from app.config import settings


def get_db_path() -> Path:
    settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return settings.DATABASE_PATH


def init_db(db_target: Path | str | sqlite3.Connection | None = None) -> None:
    """Initialize database tables and indexes."""
    if isinstance(db_target, sqlite3.Connection):
        _apply_schema(db_target)
    else:
        target_path = db_target or get_db_path()
        with sqlite3.connect(str(target_path)) as conn:
            _apply_schema(conn)


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")

    cursor = conn.cursor()

    # 1. Panel Users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS panel_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'viewer')),
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            failed_login_attempts INTEGER DEFAULT 0,
            locked_until TEXT
        );
    """)

    # 2. Audit Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL
        );
    """)

    # 3. VPN Raw Events
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vpn_raw_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            source_file TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            virtual_hub TEXT NOT NULL,
            event_type TEXT NOT NULL,
            username TEXT,
            session_id TEXT,
            connection_id TEXT,
            client_ip TEXT,
            client_port INTEGER,
            outgoing_bytes INTEGER DEFAULT 0,
            incoming_bytes INTEGER DEFAULT 0,
            raw_text TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );
    """)

    # 4. VPN Correlated Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vpn_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            virtual_hub TEXT NOT NULL,
            username TEXT NOT NULL,
            client_ip TEXT,
            client_port INTEGER,
            login_time TEXT,
            logout_time TEXT,
            duration_seconds INTEGER,
            status TEXT NOT NULL CHECK(status IN ('COMPLETED', 'ACTIVE', 'INCOMPLETE')),
            status_reason TEXT,
            outgoing_bytes INTEGER DEFAULT 0,
            incoming_bytes INTEGER DEFAULT 0,
            confidence_score REAL DEFAULT 1.0,
            source_logs TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(virtual_hub, session_id)
        );
    """)

    # 5. Sync State
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            last_modified REAL NOT NULL,
            last_byte_offset INTEGER NOT NULL,
            last_line_number INTEGER NOT NULL,
            last_synced_at TEXT NOT NULL,
            status TEXT NOT NULL,
            events_count INTEGER DEFAULT 0
        );
    """)

    # Indexes for fast querying
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_username ON vpn_sessions (username);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_hub ON vpn_sessions (virtual_hub);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_login ON vpn_sessions (login_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_logout ON vpn_sessions (logout_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_status ON vpn_sessions (status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_sessions_user_login ON vpn_sessions (username, login_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_raw_events_sess ON vpn_raw_events (session_id, virtual_hub);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vpn_raw_events_ts ON vpn_raw_events (timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at);")

    conn.commit()


@contextmanager
def get_db(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    target_path = db_path or get_db_path()
    conn = sqlite3.connect(str(target_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
