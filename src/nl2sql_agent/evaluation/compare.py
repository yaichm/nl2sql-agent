"""Compares SQL results.

Two BIRD Mini-Dev metrics: execution accuracy (binary) and Soft F1, which
gives partial credit for near-misses.
"""

from typing import Any

Row = tuple[Any, ...]


def match(predicted: list[Row] | None, gold: list[Row] | None) -> bool:
    """Execution accuracy: set(predicted) == set(gold).

    The set ignores row order and collapses duplicates. Value comparison
    stays exact — no float tolerance.

    Reference: bird-bench/mini_dev, evaluation/evaluation_ex.py
    """
    if predicted is None or gold is None:
        return False
    try:
        return set(predicted) == set(gold)
    except TypeError:
        # Unhashable value in a result row (list, dict).
        return False


def _row_match(predicted_row: Row, gold_row: Row) -> tuple[float, float, float]:
    """Row scores, normalized by the reference row's column count.

    A row is worth at most 1, whether it has 2 or 10 columns.
    """
    total = len(gold_row)
    if total == 0:
        return 0.0, 0.0, 0.0
    matches = sum(1 for v in predicted_row if v in gold_row)
    pred_only = sum(1 for v in predicted_row if v not in gold_row)
    gold_only = sum(1 for v in gold_row if v not in predicted_row)
    return matches / total, pred_only / total, gold_only / total


def soft_f1(predicted: list[Row] | None, gold: list[Row] | None) -> float:
    """Soft F1: cell-by-cell similarity, insensitive to column order.

    Positional pairing, matching the official implementation: row i of the
    prediction is compared to row i of the reference. Side effect worth
    knowing: row order matters here, unlike EX.

    Reference: bird-bench/mini_dev, evaluation/evaluation_f1.py
    """
    if not predicted and not gold:
        return 1.0
    if predicted is None or gold is None:
        return 0.0

    # Dedup while keeping first-seen order.
    p = list(dict.fromkeys(predicted))
    g = list(dict.fromkeys(gold))

    tp = fp = fn = 0.0
    for i, gold_row in enumerate(g):
        if i >= len(p):
            fn += 1.0  # expected row missing from the prediction
            continue
        m, po, go = _row_match(p[i], gold_row)
        tp += m
        fp += po
        fn += go

    fp += max(0, len(p) - len(g))  # extra rows in the prediction

    precision = tp / (tp + fp) if tp + fp > 0 else 0.0
    recall = tp / (tp + fn) if tp + fn > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
