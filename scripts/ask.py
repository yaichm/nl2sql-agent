"""Ask the baseline a question. uv run python -m scripts.ask "your question" """

import sys

from nl2sql_agent.agent.baseline import answer
from nl2sql_agent.catalog.db import admin_connection
from nl2sql_agent.catalog.format import format_schema
from nl2sql_agent.catalog.introspect import introspect
from nl2sql_agent.providers.factory import get_provider

DEFAULT = "How much did customer 6 consume in total between August and November 2013?"


def main() -> None:
    question = " ".join(sys.argv[1:]) or DEFAULT

    with admin_connection() as conn:
        tables = introspect(conn)
    schema = format_schema(tables)

    result = answer(question, schema, get_provider())

    print(f"Question : {result.question}\n")
    print(f"SQL :\n{result.sql}\n")

    if result.succeeded:
        print(f"Résultat : {result.rows}")
    else:
        print(f"Erreur : {result.error}")

    c = result.completion
    print(
        f"\n{c.prompt_tokens} tokens entrée, {c.completion_tokens} sortie, "
        f"{c.latency_s:.2f}s, {c.model}"
    )


if __name__ == "__main__":
    main()