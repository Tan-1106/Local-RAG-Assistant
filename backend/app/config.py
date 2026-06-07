from pathlib            import Path
from pydantic_settings  import BaseSettings, SettingsConfigDict
from pydantic import field_validator

# Resolve the absolute path to the project root directory where .env lives
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Resolves to Legal Assistant/
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 11520 # 8 days


    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        extra="ignore"
    )

settings = Settings()
