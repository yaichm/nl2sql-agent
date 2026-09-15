"""Freeze a sample of predictions as a regression baseline.

The output is committed. Tests replay it on every push and check the evaluation
code still produces the same numbers: if result comparison or validation breaks,
CI turns red.

    uv run python -m scripts.make_fixture reports/agent/predictions-*.json
"""

import argparse
import json
from pathlib import Path
from typing import Any

from nl2sql_agent.evaluation.evaluate import evaluate_one, summarize

FIXTURES = Path("tests/fixtures")
MAX_ROWS = 20  # large result sets do not change the measurement


def trim(rows: list[list[Any]] | None) -> list[list[Any]] | None:
    return None if rows is None else rows[:MAX_ROWS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--n", type=int, default=50)
    args = parser.parse_args()

    payload = json.loads(args.predictions.read_text(encoding="utf-8"))
    sample = payload["predictions"][: args.n]

    for pred in sample:
        pred["predicted_rows"] = trim(pred["predicted_rows"])
        pred["gold_rows"] = trim(pred["gold_rows"])

    FIXTURES.mkdir(parents=True, exist_ok=True)

    fixture = {"config": payload["config"], "predictions": sample}
    (FIXTURES / "predictions.json").write_text(
        json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = summarize([evaluate_one(p) for p in sample])
    (FIXTURES / "expected.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"{len(sample)} predictions frozen in {FIXTURES}/")
    print(f"  execution_accuracy : {summary['execution_accuracy']}")
    print(f"  soft_f1            : {summary['soft_f1']}")
    print(f"  valid_sql_rate     : {summary['valid_sql_rate']}")
    print("\nReview expected.json before committing: these numbers become the")
    print("baseline CI will defend.")


if __name__ == "__main__":
    main()