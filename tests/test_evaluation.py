"""Regression test on the measurement itself.

Replays evaluation over a frozen sample and checks the numbers have not moved.
This does not test how good the system is — it tests that the instrument
measuring it stays stable.
"""

import json
from pathlib import Path

import pytest

from nl2sql_agent.evaluation.evaluate import evaluate_one, summarize

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fixture_data() -> tuple[list[dict], dict]:
    predictions = json.loads((FIXTURES / "predictions.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    return predictions["predictions"], expected


def test_metrics_have_not_drifted(fixture_data: tuple[list[dict], dict]) -> None:
    predictions, expected = fixture_data
    summary = summarize([evaluate_one(p) for p in predictions])

    for metric in ("execution_accuracy", "soft_f1", "valid_sql_rate"):
        assert summary[metric] == expected[metric], (
            f"{metric} moved from {expected[metric]} to {summary[metric]}; "
            "if intended, regenerate the baseline with "
            "`uv run python -m scripts.make_fixture`"
        )


def test_breakdown_has_not_drifted(fixture_data: tuple[list[dict], dict]) -> None:
    predictions, expected = fixture_data
    summary = summarize([evaluate_one(p) for p in predictions])
    assert summary["breakdown"] == expected["breakdown"]


def test_categories_are_exhaustive(fixture_data: tuple[list[dict], dict]) -> None:
    # Every question falls into exactly one category.
    predictions, _ = fixture_data
    summary = summarize([evaluate_one(p) for p in predictions])
    assert sum(summary["breakdown"].values()) == summary["questions"]


def test_correct_implies_executed(fixture_data: tuple[list[dict], dict]) -> None:
    # A query cannot be correct without having run.
    predictions, _ = fixture_data
    for result in (evaluate_one(p) for p in predictions):
        if result["correct"]:
            assert result["executed"]
