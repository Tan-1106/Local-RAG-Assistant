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
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    DATA_DIR: str = "/app/data"
    DOCSTORE_PATH: str = "./storage/docstore.json"
    QDRANT_PREFER_GRPC: bool = False
    
    # Database and Authentication settings
    DATABASE_URL: str = "sqlite:////app/data/db.sqlite3"
    JWT_SECRET_KEY: str = "e8354c41ea4d3a228f4bc42a59a7ea2b73bc2a31d926343516599ef7fa9bc8bc"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 11520 # 8 days


    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH) if ENV_PATH.exists() else ".env",
        extra="ignore"
    )

settings = Settings()