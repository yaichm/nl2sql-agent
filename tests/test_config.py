"""Smoke tests for configuration loading."""

from nl2sql_agent.config import Settings


def test_defaults_are_valid() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_provider in {"mistral", "azure", "ollama"}
    assert settings.max_repairs >= 1


def test_readonly_dsn_uses_the_readonly_role() -> None:
    settings = Settings(_env_file=None, readonly_user="reader", postgres_user="owner")
    assert "reader" in settings.readonly_dsn
    assert "owner" not in settings.readonly_dsn
