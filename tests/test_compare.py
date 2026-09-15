"""Tests for result comparison.

This module decides every number the project reports, so a bug here would skew
all measurements silently.
"""

from nl2sql_agent.evaluation.compare import match, soft_f1


class TestMatch:
    """Execution accuracy, official BIRD protocol: set(predicted) == set(gold)."""

    def test_identical(self) -> None:
        rows = [("Apple", 325), ("Orange", 191)]
        assert match(rows, rows)

    def test_row_order_ignored(self) -> None:
        # The set drops ordering, even when the reference query sorts.
        assert match([(2,), (1,)], [(1,), (2,)])

    def test_duplicates_collapse(self) -> None:
        assert match([(1,), (1,), (2,)], [(1,), (2,)])

    def test_column_order_matters(self) -> None:
        # Tuples keep their internal order.
        assert not match([(325, "Apple")], [("Apple", 325)])

    def test_different_values(self) -> None:
        assert not match([(12,)], [(1847,)])

    def test_missing_row(self) -> None:
        assert not match([("Apple", 325)], [("Apple", 325), ("Orange", 191)])

    def test_floats_compared_exactly(self) -> None:
        # No tolerance: that is the official protocol, not an oversight.
        assert not match([(1847.2999999,)], [(1847.3,)])

    def test_none_is_not_a_result(self) -> None:
        assert not match(None, [(1,)])
        assert not match([(1,)], None)
        assert not match(None, None)

    def test_both_empty(self) -> None:
        assert match([], [])

    def test_unhashable_does_not_crash(self) -> None:
        # An unhashable value returns False rather than raising.
        assert not match([([1, 2],)], [(1,)])


class TestSoftF1:
    """Cell-by-cell similarity, positional row pairing."""

    def test_identical_scores_one(self) -> None:
        rows = [("Apple", 325), ("Orange", 191)]
        assert soft_f1(rows, rows) == 1.0

    def test_both_empty_scores_one(self) -> None:
        assert soft_f1([], []) == 1.0

    def test_nothing_in_common_scores_zero(self) -> None:
        assert soft_f1([(1, 2)], [(9, 9)]) == 0.0

    def test_official_example(self) -> None:
        # The example from the BIRD repo: swapped columns and missing values.
        gold = [("Apple", 325), ("Orange", None), ("Banana", 119)]
        predicted = [(325, "Apple"), (191, "Orange"), (None, "Banana")]
        assert round(soft_f1(predicted, gold), 4) == 0.6667

    def test_column_order_forgiven(self) -> None:
        # What execution accuracy scores zero, Soft F1 credits.
        gold = [("Apple", 325)]
        predicted = [(325, "Apple")]
        assert not match(predicted, gold)
        assert soft_f1(predicted, gold) == 1.0

    def test_row_order_matters(self) -> None:
        # Known limitation: the official pairing is positional.
        gold = [("Apple", 325), ("Orange", 191)]
        predicted = [("Orange", 191), ("Apple", 325)]
        assert soft_f1(predicted, gold) < 1.0

    def test_extra_row_penalised(self) -> None:
        gold = [("Apple", 325)]
        predicted = [("Apple", 325), ("Orange", 191)]
        assert 0.0 < soft_f1(predicted, gold) < 1.0

    def test_none_scores_zero(self) -> None:
        assert soft_f1(None, [(1,)]) == 0.0
        assert soft_f1([(1,)], None) == 0.0
