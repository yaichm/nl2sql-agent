"""Builds the search index.

The catalog lives in its own schema, nl2sql_catalog, so it doesn't surface
when introspecting public — otherwise the model would see its own index
table sitting alongside the business tables.
"""

import psycopg

from nl2sql_agent.catalog.introspect import Table
from nl2sql_agent.config import get_settings
from nl2sql_agent.retrieval import embed as embed_module
from nl2sql_agent.retrieval.describe import searchable_text

SCHEMA = "nl2sql_catalog"

# psycopg switches to "prepared statement" mode as soon as a parameter is
# involved, and that mode only accepts one statement. Hence a list rather
# than one big block.
DDL = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    f"DROP TABLE IF EXISTS {SCHEMA}.tables",
    f"""
    CREATE TABLE {SCHEMA}.tables (
        name        text PRIMARY KEY,
        description text NOT NULL,
        searchable  text NOT NULL,
        embedding   vector({{dim}}) NOT NULL,
        fts         tsvector GENERATED ALWAYS AS
                    (to_tsvector('english', searchable)) STORED
    )
    """,
    f"CREATE INDEX tables_embedding_idx ON {SCHEMA}.tables "
    "USING hnsw (embedding vector_cosine_ops)",
    f"CREATE INDEX tables_fts_idx ON {SCHEMA}.tables USING gin (fts)",
]


def build(
    conn: psycopg.Connection,
    tables: list[Table],
    descriptions: dict[str, str],
) -> int:
    """Rebuilds the index from scratch. Returns the number of rows written."""
    dim = get_settings().embedding_dim

    with conn.cursor() as cur:
        for statement in DDL:
            # Dimension is a type argument, not a bind parameter, so it can't
            # go through %s — we format it in instead.
            cur.execute(statement.format(dim=dim))
    conn.commit()

    texts = [searchable_text(t, descriptions.get(t.name, "")) for t in tables]
    print(f"{len(texts)} textes à embarquer…")
    vectors = embed_module.embed(texts)

    rows = [
        (t.name, descriptions.get(t.name, ""), text, embed_module.to_pgvector(vec))
        for t, text, vec in zip(tables, texts, vectors, strict=True)
    ]

    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO {SCHEMA}.tables (name, description, searchable, embedding)
            VALUES (%s, %s, %s, %s::vector)
            """,
            rows,
        )
    conn.commit()
    return len(rows)
