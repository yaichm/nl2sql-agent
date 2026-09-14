"""Descriptions des tables en langage naturel.

Le catalogue brut contient des noms opaques : atom, bond, frq_issd, A2.
Chercher dedans ne donne rien. On génère donc une description par table à
partir de sa structure et de ses valeurs d'exemple, une fois, mise en cache.

C'est ce texte qui sera indexé, pas les noms de colonnes.
"""

import json
from pathlib import Path

from nl2sql_agent.catalog.format import format_table
from nl2sql_agent.catalog.introspect import Table
from nl2sql_agent.providers.base import LLMProvider

CACHE = Path("catalog/descriptions.json")

SYSTEM_PROMPT = """Tu décris des tables de base de données pour un moteur de recherche.

Écris deux phrases maximum, en anglais, qui répondent à : que contient cette
table, et à quelle question métier permet-elle de répondre ?

Emploie le vocabulaire métier qu'un utilisateur emploierait, pas les noms de
colonnes. Si la table s'appelle `trans` et contient des mouvements bancaires,
parle de transactions, de comptes, de soldes.

Appuie-toi sur les valeurs d'exemple pour deviner le sens des colonnes obscures.

Rends uniquement la description, sans préambule ni guillemets."""


def load_descriptions() -> dict[str, str]:
    if CACHE.exists():
        data: dict[str, str] = json.loads(CACHE.read_text(encoding="utf-8"))
        return data
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def describe_one(table: Table, provider: LLMProvider) -> str:
    neighbours = ", ".join(f"{fk.references_table}" for fk in table.foreign_keys) or "aucune"

    user = (
        f"{format_table(table)}\n\n"
        f"Lignes estimées : {table.row_estimate:,}\n"
        f"Tables liées : {neighbours}"
    )
    return provider.complete(SYSTEM_PROMPT, user).text.strip()


def describe_tables(
    tables: list[Table],
    provider: LLMProvider,
    refresh: bool = False,
) -> dict[str, str]:
    """Description par table, calculée une fois puis relue du cache.

    Le cache est versionné dans catalog/ : les descriptions coûtent un appel API
    chacune, et ne changent que si le schéma change.
    """
    cache = {} if refresh else load_descriptions()
    missing = [t for t in tables if t.name not in cache]

    if not missing:
        print(f"{len(tables)} descriptions déjà en cache")
        return cache

    print(f"{len(missing)} tables à décrire ({len(cache)} déjà en cache)")
    for i, table in enumerate(missing, 1):
        cache[table.name] = describe_one(table, provider)
        print(f"\r{i}/{len(missing)}  {table.name:<28}", end="", flush=True)
        _save_cache(cache)  # écriture à chaque table : un plantage ne perd rien

    print()
    return cache


def searchable_text(table: Table, description: str) -> str:
    """Le texte indexé pour cette table.

    Assemble la description générée, le nom de la table et ceux des colonnes.
    Les noms comptent : une question qui cite un identifiant littéral doit
    pouvoir être retrouvée par la recherche lexicale.
    """
    columns = " ".join(c.name for c in table.columns)
    samples = " ".join(v for c in table.columns for v in c.sample_values[:2])
    return f"{table.name}. {description} Columns: {columns}. Values: {samples}"
