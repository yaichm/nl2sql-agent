"""Génération des prédictions. Aucune évaluation ici.

Sépare l'appel au modèle de la mesure : on peut réévaluer les mêmes prédictions
autant de fois qu'on veut sans repayer l'API. Le fichier produit est
autosuffisant — requête générée, son résultat, requête de référence, son
résultat.
"""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from nl2sql_agent.agent.baseline import answer, execute
from nl2sql_agent.evaluation.dataset import Question
from nl2sql_agent.providers.base import LLMProvider
from nl2sql_agent.retrieval.selector import SchemaSelector

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


def serializable(rows: list[tuple[Any, ...]] | None) -> list[list[Any]] | None:
    """psycopg rend des Decimal et des date : JSON ne sait pas les écrire."""
    if rows is None:
        return None
    return [
        [v if isinstance(v, (int, float, str, bool, type(None))) else str(v) for v in row]
        for row in rows
    ]


def generate_one(
    question: Question,
    selector: SchemaSelector,
    provider: LLMProvider,
    use_evidence: bool,
    gold_cache: dict[int, tuple[list[list[Any]] | None, str | None]],
) -> Prediction:
    attempt = answer(
        question.question,
        selector.select(question.question),
        provider,
        evidence=question.evidence if use_evidence else "",
    )

    # La référence ne dépend pas du modèle : une exécution par question suffit.
    if question.question_id not in gold_cache:
        rows, error = execute(question.gold_sql)
        gold_cache[question.question_id] = (serializable(rows), error)
    gold_rows, gold_error = gold_cache[question.question_id]

    return Prediction(
        question_id=question.question_id,
        db_id=question.db_id,
        difficulty=question.difficulty,
        question=question.question,
        evidence=question.evidence,
        predicted_sql=attempt.sql,
        predicted_rows=serializable(attempt.rows),
        execution_error=attempt.error,
        gold_sql=question.gold_sql,
        gold_rows=gold_rows,
        gold_error=gold_error,
        prompt_tokens=attempt.completion.prompt_tokens,
        completion_tokens=attempt.completion.completion_tokens,
        latency_s=round(attempt.completion.latency_s, 3),
    )


def generate(
    questions: list[Question],
    selector: SchemaSelector,
    provider: LLMProvider,
    tag: str,
    use_evidence: bool = True,
) -> Path:
    """Génère les prédictions et rend le chemin du fichier écrit."""
    print(
        f"{len(questions)} questions | {provider.name} / {provider.model}"
        f" | schéma: {selector.name} ({selector.tables_in_prompt} tables)"
    )

    gold_cache: dict[int, tuple[list[list[Any]] | None, str | None]] = {}
    predictions: list[Prediction] = []
    started = time.perf_counter()

    for i, question in enumerate(questions, 1):
        predictions.append(generate_one(question, selector, provider, use_evidence, gold_cache))
        failed = sum(1 for p in predictions if p.execution_error)
        print(f"\r{i}/{len(questions)}  erreurs SQL: {failed}", end="", flush=True)

    elapsed = time.perf_counter() - started
    print(f"\nTerminé en {elapsed:.0f}s")

    # Dossier nommé par le tag, fichier horodaté : deux générations avec le même
    # tag cohabitent sans s'écraser.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = REPORTS / tag
    directory.mkdir(parents=True, exist_ok=True)

    payload = {
        "config": {
            "tag": tag,
            "provider": provider.name,
            "model": provider.model,
            "mode": selector.name,
            "evidence": use_evidence,
            "tables_in_prompt": selector.tables_in_prompt,
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
    print(f"Gold en echec   : {sum(1 for p in predictions if p.gold_error)}/{n}")

    return path
