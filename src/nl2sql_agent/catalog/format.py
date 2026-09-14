"""Mise en forme du schéma pour le prompt."""

from nl2sql_agent.catalog.introspect import Table


def quote(identifier: str) -> str:
    """Entoure de guillemets tout identifiant qui n'est pas en minuscules simples.

    PostgreSQL replie les identifiants nus en minuscules. Une colonne créée
    comme "First Date" ou "aCL IgG" ne répond donc qu'à sa forme exacte,
    guillemets compris. Sans ça le modèle écrit first_date et la requête échoue.
    """
    if identifier.islower() and identifier.replace("_", "").isalnum():
        return identifier
    return f'"{identifier}"'


def format_table(table: Table) -> str:
    """Une table en DDL. Le modèle a vu des millions de CREATE TABLE."""
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

    # Virgule finale retirée sur la dernière colonne.
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
    """Le schéma complet, ou les n premières tables.

    max_tables sert quand la recherche ne renvoie que les tables pertinentes ;
    pour la baseline on passe tout.
    """
    selected = tables[:max_tables] if max_tables else tables
    return "\n\n".join(format_table(t) for t in selected)


def estimate_tokens(text: str) -> int:
    """Approximation grossière : ~4 caractères par token.

    Suffisant pour savoir si un prompt tient dans la fenêtre de contexte. Le
    compte exact vient de l'API, dans le champ usage de la réponse.
    """
    return len(text) // 4
