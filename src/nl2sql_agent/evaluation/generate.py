"""Génération des prédictions.

Sépare l'appel au modèle de la mesure : on peut ainsi réévaluer les mêmes
prédictions autant de fois qu'on veut sans repayer l'API.

Le fichier produit est autosuffisant : il contient la requête générée, son
résultat, la requête de référence et son résultat.

    uv run python -m nl2sql_agent.evaluation.generate --n 50 --tag baseline
"""

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nl2sql_agent.agent.baseline import answer, execute
from nl2sql_agent.catalog.db import admin_connection
from nl2sql_agent.catalog.format import format_schema
from nl2sql_agent.catalog.introspect import introspect
from nl2sql_agent.evaluation import dataset
from nl2sql_agent.providers.base import LLMProvider
from nl2sql_agent.providers.factory import get_provider

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


def _serializable(rows: list[tuple[Any, ...]] | None) -> list[list[Any]] | None:
    """psycopg rend des Decimal et des date : JSON ne sait pas les écrire."""
    if rows is None:
        return None
    return [
        [v if isinstance(v, (int, float, str, bool, type(None))) else str(v) for v in row]
        for row in rows
    ]


def generate_one(
    question: dataset.Question,
    schema: str,
    provider: LLMProvider,
    use_evidence: bool,
    gold_cache: dict[int, tuple[list[list[Any]] | None, str | None]],
) -> Prediction:
    attempt = answer(
        question.question,
        schema,
        provider,
        evidence=question.evidence if use_evidence else "",
    )

    # La référence ne dépend pas du modèle : une exécution par question suffit,
    # même si la même question revient dans plusieurs runs de cette session.
    if question.question_id not in gold_cache:
        rows, error = execute(question.gold_sql)
        gold_cache[question.question_id] = (_serializable(rows), error)
    gold_rows, gold_error = gold_cache[question.question_id]

    return Prediction(
        question_id=question.question_id,
        db_id=question.db_id,
        difficulty=question.difficulty,
        question=question.question,
        evidence=question.evidence,
        predicted_sql=attempt.sql,
        predicted_rows=_serializable(attempt.rows),
        execution_error=attempt.error,
        gold_sql=question.gold_sql,
        gold_rows=gold_rows,
        gold_error=gold_error,
        prompt_tokens=attempt.completion.prompt_tokens,
        completion_tokens=attempt.completion.completion_tokens,
        latency_s=round(attempt.completion.latency_s, 3),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--no-evidence", action="store_true")
    parser.add_argument("--max-tables", type=int, default=None)
    parser.add_argument("--tag", type=str, default="run", help="nom du dossier de sortie")
    args = parser.parse_args()

    questions = dataset.sample(dataset.load(), args.n)
    provider = get_provider()

    with admin_connection() as conn:
        tables = introspect(conn)
    schema = format_schema(tables, max_tables=args.max_tables)

    print(f"{len(questions)} questions | {provider.name} / {provider.model}")

    gold_cache: dict[int, tuple[list[list[Any]] | None, str | None]] = {}
    predictions: list[Prediction] = []
    started = time.perf_counter()

    for i, question in enumerate(questions, 1):
        predictions.append(
            generate_one(question, schema, provider, not args.no_evidence, gold_cache)
        )
        failed = sum(1 for p in predictions if p.execution_error)
        print(f"\r{i}/{len(questions)}  erreurs SQL: {failed}", end="", flush=True)

    elapsed = time.perf_counter() - started
    print(f"\nTerminé en {elapsed:.0f}s")

    # Dossier nommé par le tag, fichier horodaté : deux générations avec le même
    # tag cohabitent sans s'écraser.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = REPORTS / args.tag
    directory.mkdir(parents=True, exist_ok=True)

    payload = {
        "config": {
            "tag": args.tag,
            "provider": provider.name,
            "model": provider.model,
            "mode": "baseline" if args.max_tables is None else f"top-{args.max_tables}",
            "evidence": not args.no_evidence,
            "tables_in_prompt": len(tables) if args.max_tables is None else args.max_tables,
            "questions": len(questions),
            "generated_at": stamp,
            "wall_time_s": round(elapsed, 1),
        },
        "predictions": [asdict(p) for p in predictions],
    }

    path = directory / f"predictions-{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    n = len(predictions)
    total_tokens = sum(p.prompt_tokens + p.completion_tokens for p in predictions)
    gold_failed = sum(1 for p in predictions if p.gold_error)

    print(f"\nTokens total    : {total_tokens:,}")
    print(f"Tokens entree/q : {round(sum(p.prompt_tokens for p in predictions) / n)}")
    print(f"Erreurs SQL     : {sum(1 for p in predictions if p.execution_error)}/{n}")
    print(f"Gold en echec   : {gold_failed}/{n}")
    print(f"\nPredictions : {path}")


if __name__ == "__main__":
    main()
