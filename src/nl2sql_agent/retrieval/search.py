"""Recherche hybride dans le catalogue.

Deux signaux, fusionnés par RRF. Le dense comprend le sens et rattrape les
reformulations ; le lexical attrape les identifiants littéraux que les
embeddings manquent régulièrement.
"""

from dataclasses import dataclass

import psycopg

from nl2sql_agent.retrieval import embed as embed_module
from nl2sql_agent.retrieval.index import SCHEMA

# Constante du papier RRF. Elle atténue l'écart entre les premières positions :
# sans elle, la place 1 écraserait tout le reste.
RRF_K = 60

# On récupère large avant de fusionner : une table classée 20e par un signal
# peut remonter si l'autre la place bien.
CANDIDATES = 30


@dataclass
class Hit:
    name: str
    score: float
    dense_rank: int | None
    lexical_rank: int | None


def dense_search(conn: psycopg.Connection, question: str, limit: int) -> list[str]:
    """Similarité cosinus sur les embeddings. <=> est l'opérateur de pgvector."""
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
    """Recherche plein texte PostgreSQL.

    websearch_to_tsquery et plainto_tsquery joignent les termes par ET : une
    question entière n'a alors aucune chance de correspondre, puisqu'elle
    contient des mots absents du catalogue (« 6 », « 2013 »). On passe donc la
    question par to_tsvector pour obtenir ses racines, puis on les joint par OU.
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

    Travaille sur les rangs et non sur les scores : pas de normalisation entre
    des échelles incomparables, pas de poids à régler par jeu de données.
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
    """Ajoute les voisins par clé étrangère des tables retenues.

    Une jointure est impossible si un seul de ses deux côtés a été récupéré.
    Sur cette base, 35 tables sur 75 n'ont aucune clé étrangère déclarée :
    l'expansion ne couvre donc que la moitié des cas.
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
    """Les top_k tables les plus pertinentes pour cette question."""
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
