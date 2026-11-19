from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    APP_NAME: str = "SoftEther VPN Log Panel"
    APP_ENV: str = "production"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8080

    # Security
    SECRET_KEY: str = Field(
        default="development-insecure-secret-key-replace-in-production-32bytes",
        description="JWT secret key"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # Database
    DATABASE_PATH: Path = Field(
        default=Path("./data/panel.db"),
        description="Path to SQLite database file"
    )

    # SoftEther Log Directory
    SOFTETHER_LOG_DIR: Path = Field(
        default=Path("./data/sample_logs"),
        description="Root directory containing SoftEther server_log/ and security_log/"
    )

    # Sync Configuration
    SYNC_INTERVAL_SECONDS: int = 300
    AUTO_SYNC_ENABLED: bool = True
    MAX_LOG_LINE_BATCH: int = 5000

    # Rate Limiting
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_MINUTES: int = 15

    # CORS Configuration
    CORS_ORIGINS: str = Field(
        default="http://127.0.0.1:8080,http://localhost:8080,http://192.168.5.6:8080",
        description="Comma-separated allowed origins for CORS"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Ensure required local directories exist
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
