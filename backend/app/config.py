from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the absolute path to the project root directory where .env lives
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Resolves to Legal Assistant/
ENV_PATH = BASE_DIR / ".env"

class Settings(BaseSettings):
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str
    QDRANT_URL: str
    QDRANT_COLLECTION_NAME: str
    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSION: int

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        extra="ignore"
    )

settings = Settings()