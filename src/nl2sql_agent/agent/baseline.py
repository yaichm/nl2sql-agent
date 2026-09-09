"""Version naïve : schéma complet dans le prompt, une génération, une exécution.

Sert de référence. Toute amélioration ultérieure se mesure contre elle, donc ce
fichier ne bouge plus une fois la première mesure prise.
"""

import re
from dataclasses import dataclass
from typing import Any

from nl2sql_agent.catalog.db import readonly_connection
from nl2sql_agent.providers.base import Completion, LLMProvider

SYSTEM_PROMPT = """Tu écris des requêtes SQL PostgreSQL.

Règles :
- Rends uniquement la requête, sans explication ni balise Markdown.
- Une seule instruction SELECT.
- Les identifiants sont en minuscules.
- N'invente aucune table ni colonne : utilise uniquement le schéma fourni.
- Les commentaires -- ex: donnent des valeurs réelles de la colonne ; appuie-toi
  dessus pour écrire les filtres."""


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
    """Les modèles entourent souvent le SQL de balises Markdown."""
    text = raw.strip()

    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)

    return text.strip().rstrip(";").strip()


def execute(sql: str, limit: int = 1000) -> tuple[list[tuple[Any, ...]] | None, str | None]:
    """Exécute avec le rôle en lecture seule. L'erreur est retournée, pas levée."""
    try:
        with readonly_connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchmany(limit), None
    except Exception as exc:  # noqa: BLE001 - toute erreur SQL est une donnée, pas un bug
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
