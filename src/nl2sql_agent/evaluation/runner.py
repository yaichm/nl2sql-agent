"""Exécution du benchmark et production du rapport."""

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
from nl2sql_agent.evaluation.compare import has_order_by, results_match
from nl2sql_agent.evaluation.dataset import Question
from nl2sql_agent.providers.base import LLMProvider

REPORTS = Path("reports")
MAX_ROWS_SHOWN = 5


@dataclass
class Result:
    question_id: int
    db_id: str
    difficulty: str
    question: str
    predicted_sql: str
    gold_sql: str
    predicted_rows: list[list[Any]] | None
    gold_rows: list[list[Any]] | None
    correct: bool
    executed: bool
    error: str | None
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


def run_one(question: Question, schema: str, provider: LLMProvider, use_evidence: bool) -> Result:
    attempt = answer(
        question.question,
        schema,
        provider,
        evidence=question.evidence if use_evidence else "",
    )

    gold_rows, gold_error = execute(question.gold_sql)
    correct = False if gold_error else results_match(attempt.rows, gold_rows, question.gold_sql)

    return Result(
        question_id=question.question_id,
        db_id=question.db_id,
        difficulty=question.difficulty,
        question=question.question,
        predicted_sql=attempt.sql,
        gold_sql=question.gold_sql,
        predicted_rows=_serializable(attempt.rows),
        gold_rows=_serializable(gold_rows),
        correct=correct,
        executed=attempt.succeeded,
        error=attempt.error or (f"GOLD: {gold_error}" if gold_error else None),
        prompt_tokens=attempt.completion.prompt_tokens,
        completion_tokens=attempt.completion.completion_tokens,
        latency_s=round(attempt.completion.latency_s, 3),
    )


def summarize(results: list[Result]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {}

    latencies = sorted(r.latency_s for r in results)

    def pct(p: float) -> float:
        return round(latencies[min(int(p * total), total - 1)], 2)

    by_difficulty: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_difficulty.setdefault(r.difficulty, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(r.correct)

    def category(r: Result) -> str:
        if r.correct:
            return "correct"
        if r.error and r.error.startswith("GOLD:"):
            return "gold_failed"
        if not r.executed:
            return "sql_error"
        return "wrong_result"

    breakdown: dict[str, int] = {}
    for r in results:
        breakdown[category(r)] = breakdown.get(category(r), 0) + 1

    return {
        "questions": total,
        "breakdown": breakdown,
        "execution_accuracy": round(100 * sum(r.correct for r in results) / total, 1),
        "valid_sql_rate": round(100 * sum(r.executed for r in results) / total, 1),
        "by_difficulty": {
            k: {**v, "accuracy": round(100 * v["correct"] / v["total"], 1)}
            for k, v in sorted(by_difficulty.items())
        },
        "latency_p50_s": pct(0.50),
        "latency_p95_s": pct(0.95),
        "prompt_tokens_total": sum(r.prompt_tokens for r in results),
        "completion_tokens_total": sum(r.completion_tokens for r in results),
        "prompt_tokens_avg": round(sum(r.prompt_tokens for r in results) / total),
    }


def _format_rows(rows: list[list[Any]] | None) -> str:
    if rows is None:
        return "_(pas de résultat — la requête a échoué)_"
    if not rows:
        return "_(aucune ligne)_"

    shown = rows[:MAX_ROWS_SHOWN]
    body = "\n".join(
        "| " + " | ".join("NULL" if v is None else str(v) for v in r) + " |" for r in shown
    )
    width = len(shown[0])
    header = "|" + "|".join([" "] * width) + "|\n|" + "|".join(["---"] * width) + "|"
    more = (
        f"\n\n_{len(rows) - MAX_ROWS_SHOWN} lignes de plus_" if len(rows) > MAX_ROWS_SHOWN else ""
    )
    return f"{header}\n{body}{more}"


def _failure_section(r: Result) -> list[str]:
    ordered = "ordre significatif" if has_order_by(r.gold_sql) else "ordre ignoré"
    return [
        f"### {r.question_id} · {r.difficulty} · {r.db_id}",
        "",
        f"> {r.question}",
        "",
        "**Requête générée**",
        "```sql",
        r.predicted_sql,
        "```",
        "",
        "**Résultat obtenu**",
        "",
        _format_rows(r.predicted_rows),
        "",
        "**Requête de référence**",
        "```sql",
        r.gold_sql,
        "```",
        "",
        "**Résultat attendu**",
        "",
        _format_rows(r.gold_rows),
        "",
        f"_Comparaison : {ordered}._" + (f" _Erreur : {r.error}_" if r.error else ""),
        "",
        "---",
        "",
    ]


def write_report(results: list[Result], summary: dict[str, Any], config: dict[str, Any]) -> Path:
    if not summary:
        raise RuntimeError("aucun résultat à rapporter")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = REPORTS / stamp
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "run.json").write_text(
        json.dumps(
            {"config": config, "summary": summary, "results": [asdict(r) for r in results]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Run {stamp}",
        "",
        "| Paramètre | Valeur |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in config.items()],
        "",
        "| Métrique | Valeur |",
        "|---|---|",
        f"| Execution accuracy | **{summary['execution_accuracy']} %** |",
        f"| Taux de SQL valide | {summary['valid_sql_rate']} % |",
        f"| Latence p50 | {summary['latency_p50_s']} s |",
        f"| Latence p95 | {summary['latency_p95_s']} s |",
        f"| Tokens entrée / question | {summary['prompt_tokens_avg']} |",
        "",
        "| Difficulté | Correctes | Total | Accuracy |",
        "|---|---|---|---|",
        *[
            f"| {k} | {v['correct']} | {v['total']} | {v['accuracy']} % |"
            for k, v in summary["by_difficulty"].items()
        ],
        "",
        "| Issue | Questions |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(summary["breakdown"].items())],
        "",
        "## Échecs",
        "",
    ]

    failures = [r for r in results if not r.correct]
    if not failures:
        lines.append("_Aucun._")
    for r in failures:
        lines += _failure_section(r)

    lines += ["## Réussites", ""]
    successes = [r for r in results if r.correct]
    if not successes:
        lines.append("_Aucune._")
    for r in successes:
        lines += [
            f"### {r.question_id} · {r.difficulty} · {r.db_id}",
            f"> {r.question}",
            "```sql",
            r.predicted_sql,
            "```",
            _format_rows(r.predicted_rows),
            "",
        ]

    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return directory


def run(
    questions: list[Question],
    provider: LLMProvider,
    use_evidence: bool = True,
    max_tables: int | None = None,
) -> tuple[list[Result], dict[str, Any], Path]:
    if not questions:
        raise RuntimeError("aucune question à évaluer")

    with admin_connection() as conn:
        tables = introspect(conn)
    schema = format_schema(tables, max_tables=max_tables)

    results: list[Result] = []
    started = time.perf_counter()

    for i, question in enumerate(questions, 1):
        results.append(run_one(question, schema, provider, use_evidence))
        done = sum(r.correct for r in results)
        print(f"\r{i}/{len(questions)}  correctes: {done}", end="", flush=True)

    elapsed = time.perf_counter() - started
    print(f"\nTerminé en {elapsed:.0f}s")

    summary = summarize(results)
    config = {
        "provider": provider.name,
        "model": getattr(provider, "model", "?"),
        "mode": "baseline (schéma complet)" if max_tables is None else f"top-{max_tables}",
        "evidence": "oui" if use_evidence else "non",
        "tables_in_prompt": len(tables) if max_tables is None else max_tables,
    }

    return results, summary, write_report(results, summary, config)
