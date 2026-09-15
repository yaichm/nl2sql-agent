"""Provider selection from configuration."""

from nl2sql_agent.config import get_settings
from nl2sql_agent.providers.openai_compatible import OpenAICompatibleProvider

MISTRAL_URL = "https://api.mistral.ai/v1"


def get_provider() -> OpenAICompatibleProvider:
    settings = get_settings()

    if settings.llm_provider == "mistral":
        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY absente du .env")
        return OpenAICompatibleProvider(
            name="mistral",
            base_url=MISTRAL_URL,
            model=settings.llm_model,
            api_key=settings.mistral_api_key,
        )

    if settings.llm_provider == "ollama":
        return OpenAICompatibleProvider(
            name="ollama",
            base_url=f"{settings.ollama_base_url.rstrip('/')}/v1",
            model=settings.llm_model,
        )

    raise RuntimeError(f"fournisseur inconnu : {settings.llm_provider}")
