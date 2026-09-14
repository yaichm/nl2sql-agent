"""Sélection du schéma envoyé au modèle.

C'est le point de variation du projet : la baseline envoie tout, la recherche
hybride ne retient que les tables pertinentes. Le reste du pipeline ne change
pas, ce qui permet de comparer les deux à protocole identique.
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
        """Nombre de tables réellement envoyées au modèle."""
        ...

    def select(self, question: str) -> str:
        """Le texte de schéma à injecter dans le prompt pour cette question."""
        ...


class FullSchema:
    """Baseline : tout le schéma, quelle que soit la question.

    Sert de référence. Ne doit plus changer une fois la première mesure prise.
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
    """Recherche hybride : dense et lexicale fusionnées par RRF.

    Garde la trace des tables retenues par question, pour pouvoir mesurer le
    rappel contre les tables citées dans la requête de référence.
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
    """Le mode agent réutilise la recherche hybride : seule la boucle change."""
    if mode == "baseline":
        return FullSchema(tables)
    if mode in ("hybrid", "agent"):
        if conn is None:
            raise ValueError(f"le mode {mode} a besoin d'une connexion à la base")
        return HybridRetrieval(tables, conn, top_k=top_k)
    raise ValueError(f"mode inconnu : {mode}")
