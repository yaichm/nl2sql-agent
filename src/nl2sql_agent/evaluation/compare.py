"""Comparaison de résultats SQL.

Deux métriques de BIRD Mini-Dev : l'execution accuracy, binaire, et le Soft F1,
qui donne du crédit aux réponses partiellement justes.
"""

from typing import Any

Row = tuple[Any, ...]


def match(predicted: list[Row] | None, gold: list[Row] | None) -> bool:
    """Execution accuracy : set(predicted) == set(gold).

    L'usage d'un set ignore l'ordre des lignes et écrase les doublons. La
    comparaison des valeurs reste exacte, sans tolérance sur les flottants.

    Référence : bird-bench/mini_dev, evaluation/evaluation_ex.py
    """
    if predicted is None or gold is None:
        return False
    try:
        return set(predicted) == set(gold)
    except TypeError:
        # Valeur non hachable dans un résultat (list, dict).
        return False


def _row_match(predicted_row: Row, gold_row: Row) -> tuple[float, float, float]:
    """Scores d'une ligne, normalisés par le nombre de colonnes de la référence.

    Une ligne vaut donc au plus 1, qu'elle ait 2 ou 10 colonnes.
    """
    total = len(gold_row)
    if total == 0:
        return 0.0, 0.0, 0.0
    matches = sum(1 for v in predicted_row if v in gold_row)
    pred_only = sum(1 for v in predicted_row if v not in gold_row)
    gold_only = sum(1 for v in gold_row if v not in predicted_row)
    return matches / total, pred_only / total, gold_only / total


def soft_f1(predicted: list[Row] | None, gold: list[Row] | None) -> float:
    """Soft F1 : similarité cellule par cellule, insensible à l'ordre des colonnes.

    Appariement positionnel, comme l'implémentation officielle : la ligne i de
    la prédiction est comparée à la ligne i de la référence. Conséquence à
    connaître, l'ordre des lignes compte ici alors que l'EX l'ignore.

    Référence : bird-bench/mini_dev, evaluation/evaluation_f1.py
    """
    if not predicted and not gold:
        return 1.0
    if predicted is None or gold is None:
        return 0.0

    # Doublons supprimés en préservant l'ordre d'apparition.
    p = list(dict.fromkeys(predicted))
    g = list(dict.fromkeys(gold))

    tp = fp = fn = 0.0
    for i, gold_row in enumerate(g):
        if i >= len(p):
            fn += 1.0  # ligne attendue, absente de la prédiction
            continue
        m, po, go = _row_match(p[i], gold_row)
        tp += m
        fp += po
        fn += go

    fp += max(0, len(p) - len(g))  # lignes en trop dans la prédiction

    precision = tp / (tp + fp) if tp + fp > 0 else 0.0
    recall = tp / (tp + fn) if tp + fn > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
