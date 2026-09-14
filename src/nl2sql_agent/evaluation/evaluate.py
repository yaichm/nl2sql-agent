"""Évaluation d'un fichier de prédictions. Aucun appel au modèle.

Tous les taux sont exprimés entre 0 et 1.

    uv run python -m nl2sql_agent.evaluation.evaluate reports/baseline/predictions-*.json
"""

import argparse
import json
from pathlib import Path
from typing import Any

from nl2sql_agent.evaluation.compare import match, soft_f1


def _rows(raw: list[list[Any]] | None) -> list[tuple[Any, ...]] | None:
    return None if raw is None else [tuple(r) for r in raw]


def categorize(pred: dict[str, Any], correct: bool) -> str:
    """Quatre issues, qui appellent des corrections différentes."""
    if correct:
        return "correct"
    if pred["gold_error"]:
        return "gold_failed"  # défaut du benchmark, pas du système
    if pred["execution_error"]:
        return "sql_error"  # la requête n'a pas pu s'exécuter
    return "wrong_result"  # SQL valide, mais répond à côté


def evaluate_one(pred: dict[str, Any]) -> dict[str, Any]:
    correct = False
    f1 = 0.0
    if not pred["gold_error"]:
        predicted = _rows(pred["predicted_rows"])
        gold = _rows(pred["gold_rows"])
        correct = match(predicted, gold)
        f1 = round(soft_f1(predicted, gold), 4)

    return {
        "question_id": pred["question_id"],
        "db_id": pred["db_id"],
        "difficulty": pred["difficulty"],
        "correct": correct,
        "soft_f1": f1,
        "category": categorize(pred, correct),
        "executed": pred["execution_error"] is None,
        "prompt_tokens": pred["prompt_tokens"],
        "completion_tokens": pred["completion_tokens"],
        "latency_s": pred["latency_s"],
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)

    by_difficulty: dict[str, dict[str, Any]] = {}
    breakdown: dict[str, int] = {}
    for r in results:
        bucket = by_difficulty.setdefault(
            r["difficulty"], {"total": 0, "correct": 0, "f1_sum": 0.0}
        )
        bucket["total"] += 1
        bucket["correct"] += int(r["correct"])
        bucket["f1_sum"] += r["soft_f1"]
        breakdown[r["category"]] = breakdown.get(r["category"], 0) + 1

    prompt_total = sum(r["prompt_tokens"] for r in results)
    completion_total = sum(r["completion_tokens"] for r in results)
    executed = sum(r["executed"] for r in results)

    return {
        "questions": total,
        "execution_accuracy": round(sum(r["correct"] for r in results) / total, 4),
        "soft_f1": round(sum(r["soft_f1"] for r in results) / total, 4),
        "valid_sql_rate": round(executed / total, 4),
        "executed_ok": executed,
        "breakdown": {
            k: breakdown.get(k, 0) for k in ("correct", "wrong_result", "sql_error", "gold_failed")
        },
        "by_difficulty": {
            k: {
                "total": v["total"],
                "correct": v["correct"],
                "execution_accuracy": round(v["correct"] / v["total"], 4),
                "soft_f1": round(v["f1_sum"] / v["total"], 4),
            }
            for k, v in sorted(by_difficulty.items())
        },
        "latency_mean_s": round(sum(r["latency_s"] for r in results) / total, 3),
        "tokens": {
            "prompt_total": prompt_total,
            "completion_total": completion_total,
            "total": prompt_total + completion_total,
            "prompt_per_question": round(prompt_total / total),
            "completion_per_question": round(completion_total / total),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    config = payload["config"]

    results = [evaluate_one(p) for p in payload["predictions"]]
    summary = summarize(results)

    output = args.predictions.parent / args.predictions.name.replace("predictions-", "evaluation-")
    output.write_text(
        json.dumps(
            {"config": config, "summary": summary, "results": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    s = summary
    print("-" * 46)
    print(f"{config['tag']} | {config['model']} | {config['mode']}")
    print("-" * 46)
    print(f"Execution accuracy : {s['execution_accuracy']}")
    print(f"Soft F1            : {s['soft_f1']}")
    print(f"Valid SQL rate     : {s['valid_sql_rate']}  ({s['executed_ok']}/{s['questions']})")
    print(f"Latence moyenne    : {s['latency_mean_s']}s")

    print("\nVentilation")
    for name, count in s["breakdown"].items():
        print(f"  {name:<14} {count:>3}   {round(count / s['questions'], 4)}")

    print("\nPar difficulte          EX    Soft F1")
    for name, d in s["by_difficulty"].items():
        print(
            f"  {name:<13} {d['correct']:>2}/{d['total']:<3}"
            f" {d['execution_accuracy']:>6}  {d['soft_f1']:>6}"
        )

    print("\nTokens")
    print(
        f"  entree/q {s['tokens']['prompt_per_question']}"
        f" | sortie/q {s['tokens']['completion_per_question']}"
        f" | total {s['tokens']['total']:,}"
    )

    print(f"\nResultats : {output}")


if __name__ == "__main__":
    main()
