"""Hybrid retrieval over the catalog.

Two signals fused by RRF. Dense captures meaning and handles rephrasings;
lexical catches literal identifiers that embeddings routinely miss.
"""

from dataclasses import dataclass

import psycopg

from nl2sql_agent.retrieval import embed as embed_module
from nl2sql_agent.retrieval.index import SCHEMA

# Constant from the RRF paper. Softens the gap between top ranks; without it,
# position 1 would crush everything else.
RRF_K = 60

# Fetch wide before fusing: a table ranked 20th by one signal can climb back
# up if the other places it high.
CANDIDATES = 30


@dataclass
class Hit:
    name: str
    score: float
    dense_rank: int | None
    lexical_rank: int | None


def dense_search(conn: psycopg.Connection, question: str, limit: int) -> list[str]:
    """Cosine similarity on the embeddings. <=> is pgvector's operator."""
    vector = embed_module.to_pgvector(embed_module.embed_one(question))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT name
            FROM {SCHEMA}.tables
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, limit),
        )
        return [row[0] for row in cur.fetchall()]


def lexical_search(conn: psycopg.Connection, question: str, limit: int) -> list[str]:
    """PostgreSQL full-text search.

    websearch_to_tsquery and plainto_tsquery AND the terms together, which
    kills any chance of a match for a whole question — it contains words the
    catalog doesn't ("6", "2013"). We tokenize the question via to_tsvector,
    then OR the stems back together.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT name
            FROM {SCHEMA}.tables,
                 to_tsquery(
                     'english',
                     array_to_string(
                         tsvector_to_array(to_tsvector('english', %s)), ' | '
                     )
                 ) AS q
            WHERE fts @@ q
            ORDER BY ts_rank(fts, q) DESC
            LIMIT %s
            """,
            (question, limit),
        )
        return [row[0] for row in cur.fetchall()]


def rrf(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion.

    Works on ranks rather than scores: no normalization across incomparable
    scales, and no weights to tune per dataset.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, name in enumerate(ranking, start=1):
            scores[name] = scores.get(name, 0.0) + 1.0 / (k + rank)
    return scores


def expand_foreign_keys(
    names: list[str],
    edges: dict[str, set[str]],
    limit: int,
) -> list[str]:
    """Adds FK neighbours of the selected tables.

    A join is impossible if only one of its two sides has been retrieved.
    Note: 35 of 75 tables have no declared FKs on this database, so expansion
    only helps in about half the cases.
    """
    result = list(names)
    for name in names:
        for neighbour in edges.get(name, ()):
            if neighbour not in result and len(result) < limit:
                result.append(neighbour)
    return result


def search(
    conn: psycopg.Connection,
    question: str,
    top_k: int = 10,
    edges: dict[str, set[str]] | None = None,
) -> list[Hit]:
    """Top_k tables most relevant to this question."""
    dense = dense_search(conn, question, CANDIDATES)
    lexical = lexical_search(conn, question, CANDIDATES)

    scores = rrf([dense, lexical])
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    dense_pos = {name: i + 1 for i, name in enumerate(dense)}
    lexical_pos = {name: i + 1 for i, name in enumerate(lexical)}

    hits = [
        Hit(
            name=name,
            score=score,
            dense_rank=dense_pos.get(name),
            lexical_rank=lexical_pos.get(name),
        )
        for name, score in ordered[:top_k]
    ]

    if edges:
        expanded = expand_foreign_keys([h.name for h in hits], edges, top_k)
        known = {h.name for h in hits}
        hits += [
            Hit(name=n, score=0.0, dense_rank=None, lexical_rank=None)
            for n in expanded
            if n not in known
        ]

    return hits
