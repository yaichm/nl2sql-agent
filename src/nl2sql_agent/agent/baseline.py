"""Naive version: full schema in the prompt, one generation, one execution.

Serves as the reference. Every later improvement is measured against it.
"""

import re
from dataclasses import dataclass
from typing import Any

from nl2sql_agent.catalog.db import readonly_connection
from nl2sql_agent.providers.base import Completion, LLMProvider

SYSTEM_PROMPT = """Tu écris des requêtes SQL PostgreSQL.

Sortie :
- Rends uniquement la requête, sans explication ni balise Markdown.
- Une seule instruction SELECT.

Schéma :
- N'invente aucune table ni colonne : utilise uniquement le schéma fourni.
- Les identifiants entre guillemets dans le schéma en gardent : "First Date"
  s'écrit "First Date", jamais first_date.
- Dans une requête avec jointure, qualifie chaque colonne par sa table.
- Vérifie que la colonne appartient bien à la table citée : une colonne présente
  dans une table ne l'est pas forcément dans celle qui s'y joint.

Fonctions :
- N'utilise que des fonctions PostgreSQL existantes. Les notations DIVIDE(a, b),
  SUBTRACT(a, b) et MULTIPLY(a, b) qui apparaissent parfois dans l'indication
  sont de la pseudo-notation : traduis-les en a / b, a - b et a * b.
- Pour compter sous condition, écris SUM(CASE WHEN cond THEN 1 ELSE 0 END) et
  non SUM(cond) : PostgreSQL n'additionne pas les booléens.
- Pour un pourcentage ou une moyenne, force le flottant : multiplie par 100.0
  ou caste, sinon la division entière tronque.

Types :
- Les commentaires -- ex: donnent des valeurs réelles de la colonne ; appuie-toi
  dessus pour écrire les filtres et pour déduire le format.
- EXTRACT et les fonctions de date ne s'appliquent qu'aux colonnes date ou
  timestamp. Sur une colonne text, utilise SUBSTR ou LIKE.
- Ne joins que des colonnes de types compatibles."""


@dataclass
class Attempt:
    question: str
    sql: str
    rows: list[tuple[Any, ...]] | None
    error: str | None
    completion: Completion

    @property
    def succeeded(self) -> bool:
        return self.error is None


def build_prompt(question: str, schema: str, evidence: str = "") -> str:
    parts = [f"Schéma :\n\n{schema}"]
    if evidence:
        parts.append(f"Indication : {evidence}")
    parts.append(f"Question : {question}")
    parts.append("Requête SQL :")
    return "\n\n".join(parts)


def clean_sql(raw: str) -> str:
    """Models often wrap SQL in Markdown fences."""
    text = raw.strip()

    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)

    return text.strip().rstrip(";").strip()


def execute(sql: str, limit: int = 1000) -> tuple[list[tuple[Any, ...]] | None, str | None]:
    """Runs under the read-only role. Errors are returned, not raised."""
    try:
        with readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchmany(limit), None
    except Exception as exc:  # noqa: BLE001 - a SQL error is data, not a bug
        return None, str(exc).strip()


def answer(
    question: str,
    schema: str,
    provider: LLMProvider,
    evidence: str = "",
) -> Attempt:
    completion = provider.complete(SYSTEM_PROMPT, build_prompt(question, schema, evidence))
    sql = clean_sql(completion.text)
    rows, error = execute(sql)

    return Attempt(
        question=question,
        sql=sql,
        rows=rows,
        error=error,
        completion=completion,
    )
