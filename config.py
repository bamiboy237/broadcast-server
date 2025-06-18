"""
Configuration management for the broadcast server.
"""
import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Server settings
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    
    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    
    # Room settings
    room_code_length: int = 8
    max_connections_per_room: int = 100
    max_connections_per_user: int = 5
    message_history_length: int = 50
    
    # File upload settings
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_file_types: List[str] = [
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf", "text/plain", "text/csv",
        "application/json", "application/zip"
    ]
    uploads_dir: str = "uploads"
    
    # Security settings
    max_message_length: int = 1000
    max_room_id_length: int = 50
    max_user_id_length: int = 50
    rate_limit_messages_per_minute: int = 60
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_prefix = "BROADCAST_"
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_redis_url() -> str:
    """Get Redis connection URL."""
    auth = f":{settings.redis_password}@" if settings.redis_password else ""
    return f"redis://{auth}{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"


def ensure_uploads_dir() -> None:
    """Ensure uploads directory exists."""
    os.makedirs(settings.uploads_dir, exist_ok=True) 