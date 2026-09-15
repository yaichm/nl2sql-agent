"""Generates predictions. No evaluation here.

Keeps model calls separate from measurement, so the same predictions can be
re-evaluated as often as needed without paying the API again. The output
file is self-contained — generated query, its result, gold query, its result.
"""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nl2sql_agent.agent import graph as graph_module
from nl2sql_agent.agent.baseline import answer, execute
from nl2sql_agent.evaluation.dataset import Question
from nl2sql_agent.providers.base import LLMProvider
from nl2sql_agent.retrieval.selector import SchemaSelector
from nl2sql_agent.retrieval.validate import Catalog

REPORTS = Path("reports")


@dataclass
class Prediction:
    question_id: int
    db_id: str
    difficulty: str
    question: str
    evidence: str
    predicted_sql: str
    predicted_rows: list[list[Any]] | None
    execution_error: str | None
    gold_sql: str
    gold_rows: list[list[Any]] | None
    gold_error: str | None
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    attempts: int = 0


def serializable(rows: list[tuple[Any, ...]] | None) -> list[list[Any]] | None:
    """psycopg returns Decimal and date; JSON can't serialize them."""
    if rows is None:
        return None
    return [
        [v if isinstance(v, (int, float, str, bool, type(None))) else str(v) for v in row]
        for row in rows
    ]


def _gold(
    question: Question,
    cache: dict[int, tuple[list[list[Any]] | None, str | None]],
) -> tuple[list[list[Any]] | None, str | None]:
    """Gold doesn't depend on the model — one execution per question is enough."""
    if question.question_id not in cache:
        rows, error = execute(question.gold_sql)
        cache[question.question_id] = (serializable(rows), error)
    return cache[question.question_id]


def generate(
    questions: list[Question],
    selector: SchemaSelector,
    provider: LLMProvider,
    tag: str,
    use_evidence: bool = True,
    agent: bool = False,
    catalog: Catalog | None = None,
    max_attempts: int = 3,
) -> Path:
    """Generates predictions and returns the written file path.

    In agent mode, every question goes through the graph: validation, then a
    bounded repair loop. Otherwise, a single pass.
    """
    mode = "agent" if agent else selector.name
    print(
        f"{len(questions)} questions | {provider.name} / {provider.model}"
        f" | {mode} ({selector.tables_in_prompt} tables)"
    )

    compiled = None
    if agent:
        if catalog is None:
            raise ValueError("le mode agent a besoin d'un catalogue")
        compiled = graph_module.build_graph(provider, selector, catalog, max_attempts=max_attempts)

    gold_cache: dict[int, tuple[list[list[Any]] | None, str | None]] = {}
    predictions: list[Prediction] = []
    started = time.perf_counter()

    for i, question in enumerate(questions, 1):
        evidence = question.evidence if use_evidence else ""

        if compiled is not None:
            result = graph_module.answer(compiled, question.question, evidence)
            sql, rows = result.sql, result.rows
            error = result.error
            p_tokens, c_tokens = result.prompt_tokens, result.completion_tokens
            latency, attempts = result.latency_s, result.attempts
        else:
            attempt = answer(
                question.question, selector.select(question.question), provider, evidence
            )
            sql, rows = attempt.sql, attempt.rows
            error = attempt.error
            p_tokens = attempt.completion.prompt_tokens
            c_tokens = attempt.completion.completion_tokens
            latency, attempts = round(attempt.completion.latency_s, 3), 0

        gold_rows, gold_error = _gold(question, gold_cache)

        predictions.append(
            Prediction(
                question_id=question.question_id,
                db_id=question.db_id,
                difficulty=question.difficulty,
                question=question.question,
                evidence=question.evidence,
                predicted_sql=sql,
                predicted_rows=serializable(rows),
                execution_error=error,
                gold_sql=question.gold_sql,
                gold_rows=gold_rows,
                gold_error=gold_error,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
                latency_s=latency,
                attempts=attempts,
            )
        )

        failed = sum(1 for p in predictions if p.execution_error)
        retried = sum(1 for p in predictions if p.attempts)
        print(
            f"\r{i}/{len(questions)}  echecs: {failed}  reparations: {retried}", end="", flush=True
        )

    elapsed = time.perf_counter() - started
    print(f"\nTerminé en {elapsed:.0f}s")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = REPORTS / tag
    directory.mkdir(parents=True, exist_ok=True)

    payload = {
        "config": {
            "tag": tag,
            "provider": provider.name,
            "model": provider.model,
            "mode": mode,
            "evidence": use_evidence,
            "tables_in_prompt": selector.tables_in_prompt,
            "max_attempts": max_attempts if agent else 0,
            "questions": len(questions),
            "generated_at": stamp,
            "wall_time_s": round(elapsed, 1),
        },
        "predictions": [asdict(p) for p in predictions],
    }

    path = directory / f"predictions-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    n = len(predictions)
    print(f"Tokens entree/q : {round(sum(p.prompt_tokens for p in predictions) / n)}")
    print(f"Erreurs SQL     : {sum(1 for p in predictions if p.execution_error)}/{n}")
    print(f"Reparations     : {sum(p.attempts for p in predictions)}")

    return path
