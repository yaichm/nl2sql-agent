"""Natural-language table descriptions.

Raw catalog names are opaque: atom, bond, frq_issd, A2. Searching over them
yields nothing. So we generate one description per table from its structure
and sample values, once, and cache it.

That text is what gets indexed, not the column names.
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
    """Per-table description, computed once then read from cache.

    Cache lives under catalog/: each description costs one API call and only
    needs to change when the schema does.
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
        _save_cache(cache)  # flush after every table so a crash loses nothing

    print()
    return cache


def searchable_text(table: Table, description: str) -> str:
    """Indexed text for this table.

    Bundles the generated description with the table name and column names.
    Names matter: a question quoting a literal identifier still needs to be
    reachable via lexical search.
    """
    columns = " ".join(c.name for c in table.columns)
    samples = " ".join(v for c in table.columns for v in c.sample_values[:2])
    return f"{table.name}. {description} Columns: {columns}. Values: {samples}"
