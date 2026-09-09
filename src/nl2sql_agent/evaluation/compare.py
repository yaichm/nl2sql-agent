"""Comparaison de résultats SQL.

Le point délicat de l'évaluation. Deux requêtes correctes peuvent être écrites
très différemment ; on compare donc ce qu'elles retournent, pas leur texte.
"""

import math
import re
from typing import Any

Row = tuple[Any, ...]

FLOAT_TOLERANCE = 1e-6


def _normalize(value: Any) -> Any:
    """Ramène une valeur à une forme comparable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    # Decimal, date, UUID... : le texte suffit et évite les faux négatifs de type.
    return str(value).strip()


def _values_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None

    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE)

    # Un total peut sortir en float d'un côté et en Decimal-devenu-texte de l'autre.
    if isinstance(a, float) != isinstance(b, float):
        try:
            return math.isclose(
                float(a), float(b), rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE
            )
        except (TypeError, ValueError):
            return False

    return bool(a == b)


def _rows_equal(a: Row, b: Row) -> bool:
    if len(a) != len(b):
        return False
    return all(_values_equal(x, y) for x, y in zip(a, b, strict=True))


def has_order_by(sql: str) -> bool:
    """Un ORDER BY dans la requête de référence rend l'ordre significatif."""
    stripped = re.sub(r"--[^\n]*", " ", sql)
    return re.search(r"\border\s+by\b", stripped, re.IGNORECASE) is not None


def _sortable_key(row: Row) -> tuple[tuple[bool, str], ...]:
    return tuple((v is None, str(v)) for v in row)


def results_match(
    predicted: list[Row] | None,
    gold: list[Row] | None,
    gold_sql: str,
) -> bool:
    """Vrai si les deux jeux de résultats sont équivalents.

    L'ordre des lignes ne compte que si la requête de référence trie
    explicitement. L'ordre des colonnes compte toujours : c'est le protocole
    officiel de BIRD, et il est strict.
    """
    if predicted is None or gold is None:
        return False

    if len(predicted) != len(gold):
        return False

    if not predicted:
        return True

    p = [tuple(_normalize(v) for v in row) for row in predicted]
    g = [tuple(_normalize(v) for v in row) for row in gold]

    if not has_order_by(gold_sql):
        p = sorted(p, key=_sortable_key)
        g = sorted(g, key=_sortable_key)

    return all(_rows_equal(x, y) for x, y in zip(p, g, strict=True))
