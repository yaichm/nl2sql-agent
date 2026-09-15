"""Picks which schema goes into the prompt.

This is the project's variation point: baseline sends everything, hybrid
retrieval keeps only relevant tables. The rest of the pipeline is unchanged,
so both can be compared under an identical protocol.
"""

from typing import Protocol

import psycopg

from nl2sql_agent.catalog.format import format_schema
from nl2sql_agent.catalog.introspect import Table
from nl2sql_agent.retrieval import search as search_module


class SchemaSelector(Protocol):
    name: str

    @property
    def tables_in_prompt(self) -> int:
        """How many tables actually reach the model."""
        ...

    def select(self, question: str) -> str:
        """Schema text to inject into the prompt for this question."""
        ...


class FullSchema:
    """Baseline: the full schema, regardless of the question.

    Reference point. Frozen once the first measurement is taken.
    """

    name = "baseline"

    def __init__(self, tables: list[Table], max_tables: int | None = None) -> None:
        self.tables = tables
        self.max_tables = max_tables
        self._schema = format_schema(tables, max_tables=max_tables)

    @property
    def tables_in_prompt(self) -> int:
        return self.max_tables or len(self.tables)

    def select(self, question: str) -> str:
        return self._schema


class HybridRetrieval:
    """Hybrid retrieval: dense and lexical, fused by RRF.

    Tracks the tables picked per question, so recall can be measured against
    the tables cited in the gold query.
    """

    name = "hybrid"

    def __init__(
        self,
        tables: list[Table],
        conn: psycopg.Connection,
        top_k: int = 10,
        expand: bool = True,
    ) -> None:
        self.tables = {t.name: t for t in tables}
        self.conn = conn
        self.top_k = top_k
        self.selected: dict[str, list[str]] = {}

        self.edges: dict[str, set[str]] | None = None
        if expand:
            edges: dict[str, set[str]] = {}
            for table in tables:
                for fk in table.foreign_keys:
                    edges.setdefault(table.name, set()).add(fk.references_table)
                    edges.setdefault(fk.references_table, set()).add(table.name)
            self.edges = edges

    @property
    def tables_in_prompt(self) -> int:
        return self.top_k

    def select(self, question: str) -> str:
        hits = search_module.search(self.conn, question, top_k=self.top_k, edges=self.edges)
        names = [h.name for h in hits]
        self.selected[question] = names

        chosen = [self.tables[n] for n in names if n in self.tables]
        return format_schema(chosen)


def build(
    mode: str,
    tables: list[Table],
    conn: psycopg.Connection | None = None,
    top_k: int = 10,
) -> SchemaSelector:
    """Agent mode reuses hybrid retrieval; only the loop differs."""
    if mode == "baseline":
        return FullSchema(tables)
    if mode in ("hybrid", "agent"):
        if conn is None:
            raise ValueError(f"le mode {mode} a besoin d'une connexion à la base")
        return HybridRetrieval(tables, conn, top_k=top_k)
    raise ValueError(f"mode inconnu : {mode}")
