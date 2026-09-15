"""Schema formatting for the prompt."""

from nl2sql_agent.catalog.introspect import Table


def quote(identifier: str) -> str:
    """Quotes any identifier that isn't plain lowercase.

    PostgreSQL folds bare identifiers to lowercase. A column created as
    "First Date" or "aCL IgG" only responds to its exact form, quotes and
    all. Without this the model writes first_date and the query fails.
    """
    if identifier.islower() and identifier.replace("_", "").isalnum():
        return identifier
    return f'"{identifier}"'


def format_table(table: Table) -> str:
    """One table as DDL. The model has seen millions of CREATE TABLE."""
    lines = [f"CREATE TABLE {quote(table.name)} ("]

    body: list[str] = []
    for column in table.columns:
        parts = [f"  {quote(column.name)} {column.data_type}"]
        if column.is_primary_key:
            parts.append("PRIMARY KEY")

        line = " ".join(parts)
        if column.sample_values:
            line = f"{line},".ljust(48) + f"-- ex: {', '.join(column.sample_values)}"
        else:
            line = f"{line},"
        body.append(line)

    # Drop the trailing comma on the last column.
    if body:
        last = body[-1]
        if "--" in last:
            code, comment = last.split("--", 1)
            body[-1] = code.rstrip().rstrip(",").ljust(48) + "--" + comment
        else:
            body[-1] = last.rstrip().rstrip(",")

    lines.extend(body)
    lines.append(");")

    for fk in table.foreign_keys:
        lines.append(
            f"-- {quote(table.name)}.{quote(fk.column)} -> "
            f"{quote(fk.references_table)}.{quote(fk.references_column)}"
        )

    return "\n".join(lines)


def format_schema(tables: list[Table], max_tables: int | None = None) -> str:
    """The full schema, or the first n tables.

    max_tables is used when retrieval only returns the relevant tables; the
    baseline passes everything.
    """
    selected = tables[:max_tables] if max_tables else tables
    return "\n\n".join(format_table(t) for t in selected)


def estimate_tokens(text: str) -> int:
    """Rough approximation: ~4 characters per token.

    Enough to check whether a prompt fits the context window. The exact
    count comes back from the API in the response's usage field.
    """
    return len(text) // 4
