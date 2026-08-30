from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "WANDARAYA Knowledge Base"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    GOOGLE_PLACES_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    DATABASE_URL: str = "postgresql+psycopg://postgres:root@postgres:5432/wandaraya"
    REDIS_URL: str = "redis://localhost:6379"
    QDRANT_URL: str = "http://localhost:6333"
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    LANGCHAIN_TRACING_V2: bool = False
    GEMINI_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
