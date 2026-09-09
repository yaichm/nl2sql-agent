"""Connexions à la base. Deux rôles, deux fonctions."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from nl2sql_agent.config import get_settings


@contextmanager
def admin_connection() -> Iterator[psycopg.Connection]:
    """Compte propriétaire. Introspection, catalogue, migrations."""
    with psycopg.connect(get_settings().admin_dsn) as conn:
        yield conn


@contextmanager
def readonly_connection() -> Iterator[psycopg.Connection]:
    """Compte lecture seule. C'est ici que passe le SQL généré."""
    with psycopg.connect(get_settings().readonly_dsn) as conn:
        yield conn


def check_connections() -> None:
    """Vérifie que les deux rôles répondent et que le second est bien bridé."""
    with admin_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")

    with readonly_connection() as conn, conn.cursor() as cur:
        cur.execute("SHOW default_transaction_read_only")
        row = cur.fetchone()
        if row is None or row[0] != "on":
            raise RuntimeError(
                "rôle lecture seule non bridé : "
                "ALTER ROLE ... SET default_transaction_read_only = on"
            )
