"""Validation du SQL généré avant exécution.

Trois raisons de valider plutôt que de laisser PostgreSQL refuser. La sécurité,
d'abord : une requête interdite ne doit jamais atteindre la base. La qualité du
retour, ensuite : « la colonne client.date_joined n'existe pas, peut-être
customers.date » est exploitable par une boucle de correction, « syntax error »
ne l'est pas. Le coût, enfin : quelques millisecondes contre un aller-retour.
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from nl2sql_agent.catalog.introspect import Table

# Tout ce qui modifie l'état de la base. La liste est explicite plutôt que
# déduite : on préfère rater une nouveauté de PostgreSQL que la laisser passer.
FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Merge,
)


@dataclass
class Issue:
    """Un problème détecté. `suggestion` alimente le prompt de correction."""

    kind: str
    target: str
    message: str
    suggestion: str | None = None

    def __str__(self) -> str:
        text = self.message
        if self.suggestion:
            text += f" (peut-être : {self.suggestion})"
        return text


@dataclass
class Validation:
    sql: str
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def blocked(self) -> bool:
        """Un refus de sécurité est terminal : on ne tente pas de le réparer."""
        return any(i.kind in ("forbidden", "not_select") for i in self.issues)

    def as_feedback(self) -> str:
        return "\n".join(f"- {i}" for i in self.issues)


class Catalog:
    """Index des identifiants réels, pour vérifier ceux que le modèle produit.

    PostgreSQL replie les identifiants nus en minuscules, donc la comparaison se
    fait en minuscules. Les colonnes comme "aCL IgG" existent sous leur forme
    exacte : on garde les deux.
    """

    def __init__(self, tables: list[Table]) -> None:
        self.columns: dict[str, set[str]] = {}
        for table in tables:
            self.columns[table.name.lower()] = {c.name.lower() for c in table.columns}

        self.all_columns: set[str] = set()
        for names in self.columns.values():
            self.all_columns |= names

    def has_table(self, name: str) -> bool:
        return name.lower() in self.columns

    def has_column(self, column: str, table: str | None = None) -> bool:
        if table is not None:
            return column.lower() in self.columns.get(table.lower(), set())
        return column.lower() in self.all_columns

    def closest_table(self, name: str) -> str | None:
        """Suggestion par sous-chaîne : suffit pour les fautes courantes."""
        target = name.lower()
        for candidate in self.columns:
            if target in candidate or candidate in target:
                return candidate
        return None

    def tables_having(self, column: str) -> list[str]:
        target = column.lower()
        return [t for t, cols in self.columns.items() if target in cols]


def _check_forbidden(tree: exp.Expression) -> list[Issue]:
    """Une écriture peut être cachée dans une CTE ou une sous-requête.

    C'est pourquoi on parcourt tout l'arbre au lieu de regarder la racine.
    """
    issues = []
    for node in tree.walk():
        if isinstance(node, FORBIDDEN):
            issues.append(
                Issue(
                    kind="forbidden",
                    target=type(node).__name__.upper(),
                    message=f"opération interdite : {type(node).__name__.upper()}",
                )
            )
    return issues


def _check_tables(tree: exp.Expression, catalog: Catalog) -> list[Issue]:
    issues = []
    for table in tree.find_all(exp.Table):
        name = table.name
        if not name or catalog.has_table(name):
            continue
        issues.append(
            Issue(
                kind="unknown_table",
                target=name,
                message=f"la table {name} n'existe pas",
                suggestion=catalog.closest_table(name),
            )
        )
    return issues


def _alias_map(tree: exp.Expression) -> dict[str, str]:
    """Alias vers nom de table réel, pour résoudre les colonnes qualifiées."""
    aliases = {}
    for table in tree.find_all(exp.Table):
        if table.alias:
            aliases[table.alias.lower()] = table.name
        if table.name:
            aliases[table.name.lower()] = table.name
    return aliases


def _check_columns(tree: exp.Expression, catalog: Catalog) -> list[Issue]:
    """Vérifie les colonnes qualifiées, et l'existence des autres.

    Une colonne non qualifiée ne peut être rattachée à une table sans résoudre
    la portée complète de la requête : on se contente de vérifier qu'elle
    existe quelque part.
    """
    aliases = _alias_map(tree)
    issues = []

    for column in tree.find_all(exp.Column):
        name = column.name
        if not name or name == "*":
            continue

        qualifier = column.table
        if qualifier:
            table = aliases.get(qualifier.lower())
            if table is None or not catalog.has_table(table):
                continue  # la table est déjà signalée par _check_tables
            if not catalog.has_column(name, table):
                owners = catalog.tables_having(name)
                issues.append(
                    Issue(
                        kind="unknown_column",
                        target=f"{qualifier}.{name}",
                        message=f"la colonne {name} n'appartient pas à {table}",
                        suggestion=(
                            f"elle existe dans {', '.join(owners[:3])}" if owners else None
                        ),
                    )
                )
        else:
            # Une colonne non qualifiée doit appartenir à l'une des tables
            # citées par la requête. Vérifier seulement qu'elle existe quelque
            # part laisse passer le cas où le modèle oublie de joindre la table.
            in_scope = {t.name.lower() for t in tree.find_all(exp.Table)}
            candidates = set(catalog.tables_having(name))
            if not candidates & in_scope:
                issues.append(
                    Issue(
                        kind="unknown_column",
                        target=name,
                        message=(f"la colonne {name} n'appartient à aucune table de la requête"),
                        suggestion=(
                            f"elle existe dans {', '.join(sorted(candidates)[:3])}"
                            if candidates
                            else None
                        ),
                    )
                )

    return issues


def validate(sql: str, catalog: Catalog) -> Validation:
    """Parse et contrôle une requête. Ne l'exécute jamais."""
    if not sql.strip():
        return Validation(sql, [Issue("empty", "", "requête vide")])

    try:
        statements = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.ParseError as exc:
        return Validation(sql, [Issue("parse", "", f"SQL non parsable : {exc}")])

    statements = [s for s in statements if s is not None]

    if len(statements) != 1:
        return Validation(
            sql,
            [Issue("multiple", "", f"{len(statements)} instructions, une seule attendue")],
        )

    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)):
        return Validation(
            sql,
            [
                Issue(
                    kind="not_select",
                    target=type(tree).__name__,
                    message=f"seul SELECT est autorisé, reçu {type(tree).__name__}",
                )
            ],
        )

    issues = _check_forbidden(tree)
    if issues:
        return Validation(sql, issues)  # refus terminal, inutile de creuser

    issues += _check_tables(tree, catalog)
    issues += _check_columns(tree, catalog)

    return Validation(sql, issues)


def force_limit(sql: str, limit: int = 1000) -> str:
    """Ajoute un LIMIT si la requête n'en a pas.

    Garde-fou de dernier recours : une requête correcte peut ramener un million
    de lignes et saturer la mémoire du processus.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="postgres")
    except sqlglot.ParseError:
        return sql

    # Seules les Select portent un LIMIT ; pour le reste on rend la requête
    # telle quelle, la validation l'aura de toute façon rejetée.
    if not isinstance(tree, exp.Select):
        return sql
    if tree.args.get("limit") is not None:
        return sql

    return str(tree.limit(limit).sql(dialect="postgres"))
