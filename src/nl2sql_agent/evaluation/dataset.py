"""Loads the BIRD questions."""

import json
import random
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("data/raw/MINIDEV/mini_dev_postgresql.json")


@dataclass
class Question:
    question_id: int
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    difficulty: str


def load(path: Path = DEFAULT_PATH) -> list[Question]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} introuvable. Corrige DEFAULT_PATH dans dataset.py "
            f"(chemin réel : find data -name mini_dev_postgresql.json)"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Question(
            question_id=item["question_id"],
            db_id=item["db_id"],
            question=item["question"],
            evidence=item.get("evidence", ""),
            gold_sql=item["SQL"],
            difficulty=item.get("difficulty", "unknown"),
        )
        for item in raw
    ]


def sample(questions: list[Question], n: int, seed: int = 42) -> list[Question]:
    """Stratified sample by difficulty, reproducible.

    The seed is fixed so two runs on the same n cover the same questions —
    otherwise measurements wouldn't be comparable.
    """
    if n >= len(questions):
        return questions

    rng = random.Random(seed)
    by_difficulty: dict[str, list[Question]] = {}
    for q in questions:
        by_difficulty.setdefault(q.difficulty, []).append(q)

    picked: list[Question] = []
    for _, group in sorted(by_difficulty.items()):
        share = int(n * len(group) / len(questions))
        picked.extend(rng.sample(group, min(share, len(group))))

    # Floor rounding leaves a remainder; fill it at random.
    if len(picked) < n:
        chosen = {q.question_id for q in picked}
        rest = [q for q in questions if q.question_id not in chosen]
        picked.extend(rng.sample(rest, min(n - len(picked), len(rest))))

    picked.sort(key=lambda q: q.question_id)
    return picked[:n]
