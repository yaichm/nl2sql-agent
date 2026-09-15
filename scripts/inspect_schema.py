"""Prints the introspection result. uv run python -m scripts.inspect_schema"""

from nl2sql_agent.catalog.db import admin_connection, check_connections
from nl2sql_agent.catalog.introspect import introspect


def main() -> None:
    check_connections()

    with admin_connection() as conn:
        tables = introspect(conn)

    total_columns = sum(len(t.columns) for t in tables)
    total_fks = sum(len(t.foreign_keys) for t in tables)
    sampled = sum(1 for t in tables for c in t.columns if c.sample_values)

    print(f"{len(tables)} tables, {total_columns} colonnes, {total_fks} clés étrangères")
    print(f"Colonnes avec exemples : {sampled}/{total_columns}\n")

    print("Plus grosses tables :")
    for table in sorted(tables, key=lambda t: t.row_estimate, reverse=True)[:10]:
        print(f"  {table.name:<28} {table.row_estimate:>12,}")

    orphans = [t.name for t in tables if not t.primary_key]
    print(f"\nSans clé primaire : {len(orphans)}/{len(tables)}")

    isolated = [t.name for t in tables if not t.foreign_keys]
    print(f"Sans clé étrangère : {len(isolated)}/{len(tables)}")

    sample = next((t for t in tables if t.name == "yearmonth"), tables[0])
    print(f"\nDétail de '{sample.name}' ({sample.row_estimate:,} lignes) :")
    for column in sample.columns:
        flags = []
        if column.is_primary_key:
            flags.append("PK")
        if not column.nullable:
            flags.append("NOT NULL")
        suffix = f"  [{', '.join(flags)}]" if flags else ""
        examples = f"   ex: {', '.join(column.sample_values)}" if column.sample_values else ""
        print(f"  {column.name:<22} {column.data_type}{suffix}{examples}")

    for fk in sample.foreign_keys:
        print(f"  FK: {fk.column} -> {fk.references_table}.{fk.references_column}")


if __name__ == "__main__":
    main()