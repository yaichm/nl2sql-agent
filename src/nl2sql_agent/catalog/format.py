"""Mise en forme du schéma pour le prompt."""

from nl2sql_agent.catalog.introspect import Table


def format_table(table: Table) -> str:
    lines = [f"CREATE TABLE {table.name} ("]

    body: list[str] = []
    for column in table.columns:
        parts = [f"  {column.name} {column.data_type}"]
        if column.is_primary_key:
            parts.append("PRIMARY KEY")

        line = " ".join(parts)
        if column.sample_values:
            line = f"{line},".ljust(44) + f"-- ex: {', '.join(column.sample_values)}"
        else:
            line = f"{line},"
        body.append(line)

    if body:
        body[-1] = body[-1].replace(",", "", 1) if "--" not in body[-1] else body[-1]

    lines.extend(body)
    lines.append(");")

    for fk in table.foreign_keys:
        lines.append(f"-- {table.name}.{fk.column} -> {fk.references_table}.{fk.references_column}")

    return "\n".join(lines)


def format_schema(tables: list[Table], max_tables: int | None = None) -> str:
    """Le schéma complet, ou les n premières tables.

    max_tables servira quand la recherche ne renverra plus que les tables
    pertinentes ; pour la baseline on passe tout.
    """
    selected = tables[:max_tables] if max_tables else tables
    return "\n\n".join(format_table(t) for t in selected)


def estimate_tokens(text: str) -> int:
    """Approximation grossière : ~4 caractères par token.

    Suffisant pour savoir si un prompt tient dans la fenêtre de contexte.
    Le compte exact vient de l'API, dans le champ usage de la réponse.
    """
    return len(text) // 4
