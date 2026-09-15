"""Tests for SQL validation.

Two guarantees to defend: no write ever gets through, and no correct query is
rejected. The second matters as much as the first — an over-strict validator
breaks right answers.
"""

import pytest

from nl2sql_agent.catalog.introspect import Column, Table
from nl2sql_agent.retrieval.validate import Catalog, force_limit, validate


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    tables = [
        Table(
            "yearmonth",
            [
                Column("customerid", "bigint", True),
                Column("date", "text", True),
                Column("consumption", "real", True),
            ],
        ),
        Table(
            "customers", [Column("customerid", "bigint", False), Column("segment", "text", True)]
        ),
        Table("player", [Column("id", "bigint", False), Column("player_name", "text", True)]),
        Table(
            "player_attributes",
            [Column("id", "bigint", True), Column("ball_control", "bigint", True)],
        ),
        Table("examination", [Column("id", "bigint", True), Column("aCL IgG", "real", True)]),
    ]
    return Catalog(tables)


class TestAccepts:
    """A correct query must never be rejected."""

    def test_simple_select(self, catalog: Catalog) -> None:
        assert validate("SELECT consumption FROM yearmonth", catalog).ok

    def test_aggregate_with_filter(self, catalog: Catalog) -> None:
        sql = "SELECT SUM(consumption) FROM yearmonth WHERE customerid = 6"
        assert validate(sql, catalog).ok

    def test_join_with_aliases(self, catalog: Catalog) -> None:
        sql = (
            "SELECT c.segment, SUM(y.consumption) FROM customers c "
            "JOIN yearmonth y ON c.customerid = y.customerid GROUP BY c.segment"
        )
        assert validate(sql, catalog).ok

    def test_unqualified_columns_across_join(self, catalog: Catalog) -> None:
        sql = (
            "SELECT segment, consumption FROM customers "
            "JOIN yearmonth ON customers.customerid = yearmonth.customerid"
        )
        assert validate(sql, catalog).ok

    def test_quoted_identifier(self, catalog: Catalog) -> None:
        # Mixed-case columns only exist under their exact form.
        assert validate('SELECT "aCL IgG" FROM examination', catalog).ok

    def test_star(self, catalog: Catalog) -> None:
        assert validate("SELECT * FROM yearmonth", catalog).ok


class TestRejects:
    def test_unknown_table(self, catalog: Catalog) -> None:
        result = validate("SELECT * FROM salez", catalog)
        assert not result.ok
        assert result.issues[0].kind == "unknown_table"

    def test_unknown_column(self, catalog: Catalog) -> None:
        result = validate("SELECT total FROM yearmonth", catalog)
        assert not result.ok

    def test_column_from_unjoined_table(self, catalog: Catalog) -> None:
        # The model names a column without joining the table it belongs to.
        sql = (
            "SELECT SUM(CASE WHEN player_name = 'X' THEN ball_control ELSE 0 END) "
            "FROM player_attributes"
        )
        assert not validate(sql, catalog).ok

    def test_column_from_wrong_table(self, catalog: Catalog) -> None:
        result = validate("SELECT pa.player_name FROM player_attributes pa", catalog)
        assert not result.ok
        assert "player" in str(result.issues[0])

    def test_empty(self, catalog: Catalog) -> None:
        assert not validate("   ", catalog).ok

    def test_two_statements(self, catalog: Catalog) -> None:
        assert not validate("SELECT 1; SELECT 2", catalog).ok


class TestBlocks:
    """Security refusals are terminal: never sent back for repair."""

    @pytest.mark.parametrize(
        "sql",
        [
            "DROP TABLE yearmonth",
            "DELETE FROM yearmonth",
            "UPDATE yearmonth SET consumption = 0",
            "INSERT INTO yearmonth VALUES (1, '1', 1)",
            "TRUNCATE yearmonth",
            "CREATE TABLE evil (id int)",
            "ALTER TABLE yearmonth ADD COLUMN evil text",
        ],
    )
    def test_writes_are_blocked(self, catalog: Catalog, sql: str) -> None:
        result = validate(sql, catalog)
        assert not result.ok
        assert result.blocked

    def test_write_hidden_in_cte(self, catalog: Catalog) -> None:
        # String matching on SQL would let this one through.
        sql = "WITH x AS (DELETE FROM yearmonth RETURNING 1) SELECT * FROM x"
        result = validate(sql, catalog)
        assert not result.ok
        assert result.blocked

    def test_valid_select_is_not_blocked(self, catalog: Catalog) -> None:
        assert not validate("SELECT consumption FROM yearmonth", catalog).blocked


class TestForceLimit:
    def test_adds_limit(self) -> None:
        assert "LIMIT 1000" in force_limit("SELECT * FROM yearmonth")

    def test_keeps_existing_limit(self) -> None:
        assert force_limit("SELECT * FROM yearmonth LIMIT 5").endswith("LIMIT 5")

    def test_leaves_unparsable_sql_alone(self) -> None:
        broken = "SELECT FROM WHERE"
        assert force_limit(broken) == broken
