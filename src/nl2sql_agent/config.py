"""Central configuration, loaded once from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Values come from the environment or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM provider
    llm_provider: Literal["mistral", "azure", "ollama"] = "mistral"
    llm_model: str = "mistral-large-latest"
    mistral_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Embeddings, run locally
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "nl2sql"
    postgres_user: str = "postgres"
    postgres_password: str = "changeme"
    readonly_user: str = "nl2sql_reader"
    readonly_password: str = "changeme"
    statement_timeout_ms: int = 10_000

    # Agent behaviour
    max_repairs: int = 3
    retrieval_top_k: int = 10
    forced_row_limit: int = 1_000
    explain_cost_threshold: float = 1_000_000

    # Observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    mlflow_tracking_uri: str = "http://localhost:5000"

    @property
    def admin_dsn(self) -> str:
        """Connection string for the owner role, used for indexing and migrations."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def readonly_dsn(self) -> str:
        """Connection string used to execute generated SQL. SELECT only."""
        return (
            f"postgresql://{self.readonly_user}:{self.readonly_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton settings instance."""
    return Settings()
