from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "WANDARAYA Knowledge Base"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    GOOGLE_PLACES_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    OPENWEATHERMAP_API_KEY: str = ""
    OPENWEATHERMAP_API_KEY: str = ""
    DATABASE_URL: str = "postgresql+psycopg://postgres:root@postgres:5432/wandaraya"
    REDIS_URL: str = "redis://redis:6379"
    QDRANT_URL: str = "http://qdrant:6333"
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    LANGCHAIN_TRACING_V2: bool = False
    GEMINI_API_KEY: str = ""
    AIRFLOW_API_TOKEN: str = ""
    ROUTE_API_BASE_URL: str = "https://api.openrouteservice.org"
    ROUTE_API_KEY: str = ""
    ORS_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    # Stage 12.4G research controls. Evidence composition is deliberately
    # opt-in and can never imply permission to change production ordering.
    ENABLE_EXPERIMENTAL_SEASONALITY_EVIDENCE: bool = False
    ENABLE_EXPERIMENTAL_CONTEXT_COMPOSITION: bool = False
    ENABLE_SEASONALITY_PRODUCTION_RERANKING: bool = False
    # Stage 12.5 is an internal research-only four-layer engine. Every switch
    # is opt-in and the production-ranking switch is a hard safety guard.
    ENABLE_UNIFIED_CONTEXT_ENGINE: bool = False
    ENABLE_UNIFIED_CONTEXT_EXPERIMENTAL_RERANKING: bool = False
    ENABLE_UNIFIED_CONTEXT_RESEARCH_API: bool = False
    ENABLE_UNIFIED_CONTEXT_PRODUCTION_RANKING: bool = False
    UNIFIED_CONTEXT_RESEARCH_API_TOKEN: str = ""
    UNIFIED_CONTEXT_MAX_CANDIDATES: int = 50
    UNIFIED_CONTEXT_ADAPTER_TIMEOUT_SECONDS: float = 15.0
    UNIFIED_CONTEXT_SEMANTIC_RETRIEVAL_TIMEOUT_SECONDS: float = 20.0
    # Stage 12.6 agentic research controls. These are independent of the
    # Stage 12.5 flags and never authorize production routing.
    ENABLE_LANGGRAPH_RECOMMENDATION_ENGINE: bool = False
    ENABLE_LANGGRAPH_RESEARCH_API: bool = False
    ALLOW_LOCAL_DEVELOPMENT_RESEARCH_ACCESS: bool = False
    ENABLE_LANGCHAIN_INTENT_EXTRACTION: bool = False
    ENABLE_LANGCHAIN_LLM_EXPLANATIONS: bool = False
    ENABLE_GROUP_EMOTION_CONTEXT: bool = False
    ENABLE_R4_EXPERIMENTAL_RERANKING: bool = False
    ENABLE_LANGGRAPH_PRODUCTION_ROUTING: bool = False
    LANGGRAPH_RESEARCH_API_TOKEN: str = ""
    LANGGRAPH_MAX_CLARIFICATION_TURNS: int = 3
    # Four context adapters can each consume their isolated timeout budget.
    LANGGRAPH_EXECUTION_TIMEOUT_SECONDS: float = 120.0
    LANGGRAPH_SESSION_TTL_SECONDS: int = 3600
    LANGCHAIN_INTENT_MODEL: str = "llama-3.3-70b-versatile"

    @property
    def effective_route_api_key(self) -> str:
        return self.ROUTE_API_KEY or self.ORS_API_KEY

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
