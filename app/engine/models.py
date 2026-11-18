from dataclasses import dataclass, field
from enum import Enum
import hashlib


class EventType(str, Enum):
    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAIL = "AUTH_FAIL"
    SESSION_CREATED = "SESSION_CREATED"
    SESSION_TERMINATED = "SESSION_TERMINATED"
    CONN_CREATED = "CONN_CREATED"
    CONN_TERMINATED = "CONN_TERMINATED"
    SERVER_START = "SERVER_START"
    SERVER_STOP = "SERVER_STOP"
    UNKNOWN = "UNKNOWN"


class SessionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    ACTIVE = "ACTIVE"
    INCOMPLETE = "INCOMPLETE"


@dataclass
class RawLogEvent:
    source_file: str
    source_line: int
    timestamp: str  # YYYY-MM-DD HH:MM:SS or YYYY-MM-DD HH:MM:SS.sss
    virtual_hub: str  # e.g. "DEFAULT", "VPN" or "SERVER"
    event_type: EventType
    username: str | None = None
    session_id: str | None = None
    connection_id: str | None = None
    client_ip: str | None = None
    client_port: int | None = None
    outgoing_bytes: int = 0
    incoming_bytes: int = 0
    raw_text: str = ""
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint()

    def compute_fingerprint(self) -> str:
        """
        Compute a stable fingerprint for event deduplication.
        If both server_log and security_log log the same event,
        this will yield identical fingerprints so we don't duplicate events.
        """
        ts = self.timestamp.strip()
        hub = (self.virtual_hub or "").strip().upper()
        etype = self.event_type.value
        user = (self.username or "").strip().lower()
        sess = (self.session_id or "").strip().upper()
        conn = (self.connection_id or "").strip().upper()
        ip = (self.client_ip or "").strip()
        
        # Primary key payload
        key = f"{ts}|{hub}|{etype}|{user}|{sess}|{conn}|{ip}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()


@dataclass
class CorrelatedSession:
    session_id: str
    virtual_hub: str
    username: str
    client_ip: str | None = None
    client_port: int | None = None
    login_time: str | None = None
    logout_time: str | None = None
    duration_seconds: int | None = None
    status: SessionStatus = SessionStatus.INCOMPLETE
    status_reason: str | None = None
    outgoing_bytes: int = 0
    incoming_bytes: int = 0
    confidence_score: float = 1.0
    source_logs: list[str] = field(default_factory=list)

    def calculate_duration(self) -> None:
        """Calculate duration if both login_time and logout_time are present."""
        if self.login_time and self.logout_time:
            from datetime import datetime
            try:
                # Handle possible sub-second precision
                t_in = self.login_time.split(".")[0]
                t_out = self.logout_time.split(".")[0]
                dt_in = datetime.strptime(t_in, "%Y-%m-%d %H:%M:%S")
                dt_out = datetime.strptime(t_out, "%Y-%m-%d %H:%M:%S")
                delta = int((dt_out - dt_in).total_seconds())
                if delta >= 0:
                    self.duration_seconds = delta
                else:
                    self.duration_seconds = 0
            except Exception:
                self.duration_seconds = None
