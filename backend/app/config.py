from pathlib            import Path
from typing             import Literal
from pydantic           import field_validator, model_validator
from pydantic_settings  import BaseSettings, SettingsConfigDict

# Resolve the absolute path to the project root directory where .env lives
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Resolves to Local RAG Assistant/
ENV_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    """
    Application configuration settings loaded from environment variables or .env file.
    Provides typing and validation for environment variables used throughout the application.
    """
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    QDRANT_URL: str
    QDRANT_COLLECTION_NAME: str
    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSION: int
    ALLOWED_ORIGINS: str
    REDIS_URL: str = "redis://localhost:6379/0"
    RQ_QUEUE_NAME: str = "document-ingestion"
    RQ_JOB_TIMEOUT_SECONDS: int = 3600
    RQ_RESULT_TTL_SECONDS: int = 86400
    RQ_FAILURE_TTL_SECONDS: int = 604800
    RAG_WRITE_LOCK_TIMEOUT_SECONDS: int = 3900
    RAG_WRITE_LOCK_WAIT_SECONDS: int = 60

    @field_validator("JWT_SECRET_KEY", "SUPER_ADMIN_PASSWORD", mode="after")
    @classmethod
    def validate_secrets(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Secret keys and passwords must be at least 8 characters long")
        return v

    DATA_DIR: str = "/app/data"
    DOCSTORE_PATH: str = "./storage/docstore.json"
    QDRANT_PREFER_GRPC: bool = False
    
    # Database and Authentication settings
    DATABASE_URL: str = "sqlite:////app/data/db.sqlite3"
    JWT_SECRET_KEY: str
    SUPER_ADMIN_USERNAME: str
    SUPER_ADMIN_PASSWORD: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    AUTH_COOKIE_NAME: str = "local_rag_assistant_session"
    AUTH_REFRESH_COOKIE_NAME: str = "local_rag_assistant_refresh"
    AUTH_CSRF_COOKIE_NAME: str = "local_rag_assistant_csrf"
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    AUTH_COOKIE_PATH: str = "/api"
    APP_ENV: Literal["development", "test", "production"] = "development"
    TRUST_PROXY_HEADERS: bool = False

    UPLOAD_MAX_FILES: int = 10
    UPLOAD_MAX_FILE_MB: int = 10
    UPLOAD_MAX_TOTAL_MB: int = 50
    UPLOAD_CHUNK_SIZE_BYTES: int = 1024 * 1024

    RATE_LIMIT_LOGIN_IP_PER_MINUTE: int = 5
    RATE_LIMIT_LOGIN_USERNAME_PER_15_MINUTES: int = 10
    RATE_LIMIT_REGISTER_IP_PER_HOUR: int = 3
    RATE_LIMIT_CHAT_USER_PER_MINUTE: int = 20
    RATE_LIMIT_UPLOAD_ADMIN_PER_10_MINUTES: int = 5

    @model_validator(mode="after")
    def validate_cookie_settings(self):
        if self.AUTH_COOKIE_SAMESITE == "none" and not self.AUTH_COOKIE_SECURE:
            raise ValueError("AUTH_COOKIE_SECURE must be true when AUTH_COOKIE_SAMESITE is 'none'")
        if self.APP_ENV == "production":
            if not self.AUTH_COOKIE_SECURE:
                raise ValueError("AUTH_COOKIE_SECURE must be true in production")
            origins = [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
            if "*" in origins:
                raise ValueError("Wildcard ALLOWED_ORIGINS is forbidden in production")
            if any(not origin.startswith("https://") for origin in origins if origin):
                raise ValueError("Production ALLOWED_ORIGINS must use HTTPS")
        if self.UPLOAD_MAX_TOTAL_MB < self.UPLOAD_MAX_FILE_MB:
            raise ValueError("UPLOAD_MAX_TOTAL_MB must be >= UPLOAD_MAX_FILE_MB")
        return self

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        extra="ignore"
    )

settings = Settings()
