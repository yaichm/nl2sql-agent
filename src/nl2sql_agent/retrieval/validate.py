"""Validates generated SQL before it runs.

Three reasons to validate rather than let PostgreSQL reject. Security first:
a forbidden query must never reach the database. Feedback quality next:
"column client.date_joined does not exist, maybe customers.date" is
actionable by a repair loop, "syntax error" is not. Cost last: a few
milliseconds versus a round-trip.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from nl2sql_agent.catalog.introspect import Table

# Anything that mutates DB state. Listed explicitly rather than inferred:
# better to miss a new PostgreSQL feature than to let one slip through.
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Merge,
)


@dataclass
class Issue:
    """A detected problem. `suggestion` feeds the repair prompt."""

    kind: str
    target: str
    message: str
    suggestion: str | None = None

    def __str__(self) -> str:
        text = self.message
        if self.suggestion:
            text += f" (peut-être : {self.suggestion})"
        return text


@dataclass
class Validation:
    sql: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def blocked(self) -> bool:
        """A security refusal is terminal — we don't try to repair it."""
        return any(i.kind in ("forbidden", "not_select") for i in self.issues)

    def as_feedback(self) -> str:
        return "\n".join(f"- {i}" for i in self.issues)


class Catalog:
    """Index of real identifiers, used to check the ones the model produces.

    PostgreSQL folds bare identifiers to lowercase, so comparisons are done
    in lowercase. Columns like "aCL IgG" only exist under their exact form,
    so we keep both.
    """

    def __init__(self, tables: list[Table]) -> None:
        self.columns: dict[str, set[str]] = {}
        for table in tables:
            self.columns[table.name.lower()] = {c.name.lower() for c in table.columns}

        self.all_columns: set[str] = set()
        for names in self.columns.values():
            self.all_columns |= names

    def has_table(self, name: str) -> bool:
        return name.lower() in self.columns

    def has_column(self, column: str, table: str | None = None) -> bool:
        if table is not None:
            return column.lower() in self.columns.get(table.lower(), set())
        return column.lower() in self.all_columns

    def closest_table(self, name: str) -> str | None:
        """Substring-based suggestion — good enough for common typos."""
        target = name.lower()
        for candidate in self.columns:
            if target in candidate or candidate in target:
                return candidate
        return None

    def tables_having(self, column: str) -> list[str]:
        target = column.lower()
        return [t for t, cols in self.columns.items() if target in cols]


def _check_forbidden(tree: exp.Expression) -> list[Issue]:
    """A write can hide inside a CTE or a subquery.

    That's why we walk the whole tree instead of only checking the root.
    """
    issues = []
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            issues.append(
                Issue(
                    kind="forbidden",
                    target=type(node).__name__.upper(),
                    message=f"opération interdite : {type(node).__name__.upper()}",
                )
            )
    return issues


def _check_tables(tree: exp.Expression, catalog: Catalog) -> list[Issue]:
    issues = []
    for table in tree.find_all(exp.Table):
        name = table.name
        if not name or catalog.has_table(name):
            continue
        issues.append(
            Issue(
                kind="unknown_table",
                target=name,
                message=f"la table {name} n'existe pas",
                suggestion=catalog.closest_table(name),
            )
        )
    return issues


def _alias_map(tree: exp.Expression) -> dict[str, str]:
    """Alias to real table name, for resolving qualified columns."""
    aliases = {}
    for table in tree.find_all(exp.Table):
        if table.alias:
            aliases[table.alias.lower()] = table.name
        if table.name:
            aliases[table.name.lower()] = table.name
    return aliases


def _check_columns(tree: exp.Expression, catalog: Catalog) -> list[Issue]:
    """Checks qualified columns, and that the others exist.

    An unqualified column can't be tied to a specific table without resolving
    the query's full scope, so we just check it exists somewhere.
    """
    aliases = _alias_map(tree)
    issues = []

    for column in tree.find_all(exp.Column):
        name = column.name
        if not name or name == "*":
            continue

        qualifier = column.table
        if qualifier:
            table = aliases.get(qualifier.lower())
            if table is None or not catalog.has_table(table):
                continue  # table already flagged by _check_tables
            if not catalog.has_column(name, table):
                owners = catalog.tables_having(name)
                issues.append(
                    Issue(
                        kind="unknown_column",
                        target=f"{qualifier}.{name}",
                        message=f"la colonne {name} n'appartient pas à {table}",
                        suggestion=(
                            f"elle existe dans {', '.join(owners[:3])}" if owners else None
                        ),
                    )
                )
        else:
            # An unqualified column must belong to one of the tables the
            # query cites. Just checking it exists somewhere would let
            # through the case where the model forgot to join the table.
            in_scope = {t.name.lower() for t in tree.find_all(exp.Table)}
            candidates = set(catalog.tables_having(name))
            if not candidates & in_scope:
                issues.append(
                    Issue(
                        kind="unknown_column",
                        target=name,
                        message=(f"la colonne {name} n'appartient à aucune table de la requête"),
                        suggestion=(
                            f"elle existe dans {', '.join(sorted(candidates)[:3])}"
                            if candidates
                            else None
                        ),
                    )
                )

    return issues


def validate(sql: str, catalog: Catalog) -> Validation:
    """Parses and checks a query. Never runs it."""
    if not sql.strip():
        return Validation(sql, [Issue("empty", "", "requête vide")])

    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.ParseError as exc:
        return Validation(sql, [Issue("parse", "", f"SQL non parsable : {exc}")])

    statements = [s for s in statements if s is not None]

    if len(statements) != 1:
        return Validation(
            sql,
            [Issue("multiple", "", f"{len(statements)} instructions, une seule attendue")],
        )

    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        return Validation(
            sql,
            [
                Issue(
                    kind="not_select",
                    target=type(tree).__name__,
                    message=f"seul SELECT est autorisé, reçu {type(tree).__name__}",
                )
            ],
        )

    issues = _check_forbidden(tree)
    if issues:
        return Validation(sql, issues)  # terminal refusal, no point digging

    issues += _check_tables(tree, catalog)
    issues += _check_columns(tree, catalog)

    return Validation(sql, issues)


def force_limit(sql: str, limit: int = 1000) -> str:
    """Adds a LIMIT if the query has none.

    Last-resort guardrail: a perfectly correct query can return a million
    rows and blow up process memory.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.ParseError:
        return sql

    # Only Select carries a LIMIT; for anything else we return the query
    # as-is — validation will have rejected it already.
    if not isinstance(tree, exp.Select):
        return sql
    if tree.args.get("limit") is not None:
        return sql

    return str(tree.limit(limit).sql(dialect="postgres"))
