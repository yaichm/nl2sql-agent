
from nl2sql_agent.catalog.db import admin_connection
from nl2sql_agent.catalog.format import estimate_tokens, format_schema, format_table
from nl2sql_agent.catalog.introspect import introspect


def main() -> None:
    with admin_connection() as conn:
        tables = introspect(conn)

    sample = next((t for t in tables if t.name == "yearmonth"), tables[0])
    print(format_table(sample))
    print()

    full = format_schema(tables)
    print(f"Schéma complet : {len(full):,} caractères, ~{estimate_tokens(full):,} tokens")

    ten = format_schema(tables, max_tables=10)
    print(f"Dix tables     : {len(ten):,} caractères, ~{estimate_tokens(ten):,} tokens")


if __name__ == "__main__":
    main()