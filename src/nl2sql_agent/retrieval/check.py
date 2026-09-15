"""Validation diagnostic on already-produced predictions.

Replays validation over a predictions.json without calling the model: how
many SQL errors would have been caught before execution, and how many
correct queries would be wrongly rejected.
"""

import json
from pathlib import Path
from typing import Any

import psycopg

from nl2sql_agent.catalog.introspect import introspect
from nl2sql_agent.evaluation.compare import match
from nl2sql_agent.retrieval.validate import Catalog, validate


def _rows(raw: list[list[Any]] | None) -> list[tuple[Any, ...]] | None:
    return None if raw is None else [tuple(r) for r in raw]


def check_predictions(conn: psycopg.Connection, path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    catalog = Catalog(introspect(conn, with_samples=False))

    caught = missed = false_positive = clean = 0
    examples: list[str] = []

    for pred in payload["predictions"]:
        result = validate(pred["predicted_sql"], catalog)
        failed = pred["execution_error"] is not None
        correct = match(_rows(pred["predicted_rows"]), _rows(pred["gold_rows"]))

        if failed and not result.ok:
            caught += 1
            if len(examples) < 5:
                examples.append(f"{pred['question_id']} détectée : {result.issues[0]}")
        elif failed and result.ok:
            missed += 1
            if len(examples) < 8:
                examples.append(
                    f"{pred['question_id']} manquée : {(pred['execution_error'] or '')[:90]}"
                )
        elif correct and not result.ok:
            # The costly case: validation rejecting a correct query.
            false_positive += 1
            examples.append(f"{pred['question_id']} FAUX POSITIF : {result.issues[0]}")
        else:
            clean += 1

    total_failed = caught + missed
    return {
        "questions": len(payload["predictions"]),
        "sql_errors": total_failed,
        "caught": caught,
        "missed": missed,
        "detection_rate": round(caught / total_failed, 3) if total_failed else 0.0,
        "false_positives": false_positive,
        "clean": clean,
        "examples": examples,
    }


def report(result: dict[str, Any]) -> None:
    print("-" * 46)
    print(f"Questions             : {result['questions']}")
    print(f"Erreurs SQL           : {result['sql_errors']}")
    print(f"  detectees            {result['caught']}")
    print(f"  manquees             {result['missed']}")
    print(f"Taux de detection     : {result['detection_rate']}")
    print(f"Faux positifs         : {result['false_positives']}")

    if result["examples"]:
        print("\nDetail")
        for line in result["examples"]:
            print(f"  {line}")
