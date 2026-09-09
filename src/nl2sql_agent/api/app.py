"""API FastAPI et page de démonstration."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from nl2sql_agent.agent.baseline import answer
from nl2sql_agent.catalog.db import admin_connection
from nl2sql_agent.catalog.format import format_schema
from nl2sql_agent.catalog.introspect import introspect
from nl2sql_agent.providers.factory import get_provider

app = FastAPI(title="NL→SQL Agent", version="0.1.0")

STATIC = Path(__file__).parent / "static"


@lru_cache(maxsize=1)
def cached_schema() -> str:
    """L'introspection prend ~30s à cause de l'échantillonnage. Une fois suffit."""
    with admin_connection() as conn:
        tables = introspect(conn)
    return format_schema(tables)


class Question(BaseModel):
    question: str
    evidence: str = ""


class Answer(BaseModel):
    question: str
    sql: str
    rows: list[list[Any]] | None = None
    columns: list[str] | None = None
    error: str | None = None
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    model: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query", response_model=Answer)
def query(payload: Question) -> Answer:
    result = answer(payload.question, cached_schema(), get_provider(), payload.evidence)
    c = result.completion

    return Answer(
        question=result.question,
        sql=result.sql,
        rows=[list(r) for r in result.rows] if result.rows else None,
        error=result.error,
        prompt_tokens=c.prompt_tokens,
        completion_tokens=c.completion_tokens,
        latency_s=round(c.latency_s, 2),
        model=c.model,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")
