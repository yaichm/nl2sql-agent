"""Construction de l'index de recherche.

Le catalogue vit dans un schéma séparé, nl2sql_catalog, pour ne pas apparaître
dans l'introspection de public : sinon le modèle verrait sa propre table
d'index parmi les tables métier.
"""

import psycopg

from nl2sql_agent.catalog.introspect import Table
from nl2sql_agent.config import get_settings
from nl2sql_agent.retrieval import embed as embed_module
from nl2sql_agent.retrieval.describe import searchable_text

SCHEMA = "nl2sql_catalog"

# psycopg passe en mode "prepared statement" dès qu'il y a un paramètre, et
# celui-ci n'accepte qu'une instruction. D'où la liste plutôt qu'un bloc unique.
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
    """Reconstruit l'index depuis zéro. Rend le nombre d'entrées écrites."""
    dim = get_settings().embedding_dim

    with conn.cursor() as cur:
        for statement in DDL:
            # La dimension est une valeur de type, pas un paramètre : elle ne
            # peut pas passer par %s, d'où le format.
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
