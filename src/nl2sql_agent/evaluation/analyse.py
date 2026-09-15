"""Compares evaluation runs.

Reads every evaluation-*.json under reports/, keeps the latest per tag, and
outputs a comparison table plus three charts.

    uv run nl2sql analyse
    uv run nl2sql analyse --tags baseline hybrid
"""

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no display server here
import matplotlib.pyplot as plt  # noqa: E402

REPORTS = Path("reports")
OUTPUT = REPORTS / "analysis"

DIFFICULTIES = ("simple", "moderate", "challenging")

# Green, orange, red, grey: correct, wrong answer, failed, benchmark bug.
ACCENT = "#2d5f8b"


def load_runs(tags: list[str] | None) -> list[dict[str, Any]]:
    """Latest run per tag, sorted alphabetically by tag."""
    latest: dict[str, tuple[str, dict[str, Any]]] = {}

    for path in sorted(REPORTS.glob("*/evaluation-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        tag = payload["config"]["tag"]
        stamp = payload["config"]["generated_at"]
        if tag not in latest or stamp > latest[tag][0]:
            latest[tag] = (stamp, payload)

    runs = [payload for _, payload in latest.values()]
    if tags:
        runs = [r for r in runs if r["config"]["tag"] in tags]
    return sorted(runs, key=lambda r: r["config"]["tag"])


def print_table(runs: list[dict[str, Any]]) -> str:
    """Markdown table, printed and returned so it can be written to disk."""
    header = (
        "| Run | Modèle | Tables | EX | Soft F1 | Tokens/q | Latence |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = ""
    for run in runs:
        c, s = run["config"], run["summary"]
        rows += (
            f"| {c['tag']} | {c['model']} | {c['tables_in_prompt']} "
            f"| **{s['execution_accuracy']}** | {s['soft_f1']} "
            f"| {s['tokens']['prompt_per_question']} | {s['latency_mean_s']}s |\n"
        )
    table = header + rows
    print(table)
    return table


def _question_count(runs: list[dict[str, Any]]) -> int:
    """Compared runs must cover the same sample."""
    return int(runs[0]["summary"]["questions"])


def _style(ax: Any) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)


def chart_accuracy(runs: list[dict[str, Any]]) -> None:
    """EX and Soft F1 side by side, one group per run."""
    tags = [r["config"]["tag"] for r in runs]
    ex = [r["summary"]["execution_accuracy"] for r in runs]
    f1 = [r["summary"]["soft_f1"] for r in runs]

    x = range(len(tags))
    width = 0.38

    fig, ax = plt.subplots(figsize=(1.8 * len(tags) + 3, 4.2))
    b1 = ax.bar([i - width / 2 for i in x], ex, width, label="Execution accuracy", color=ACCENT)
    b2 = ax.bar([i + width / 2 for i in x], f1, width, label="Soft F1", color=ACCENT, alpha=0.45)

    for bars in (b1, b2):
        ax.bar_label(bars, fmt="%.3f", fontsize=8, padding=2)

    ax.set_xticks(list(x))
    ax.set_xticklabels(tags)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.set_title(f"Exactitude par run ({_question_count(runs)} questions)")
    ax.legend(frameon=False, fontsize=9)
    _style(ax)

    fig.tight_layout()
    fig.savefig(OUTPUT / "accuracy.png", dpi=150)
    plt.close(fig)


def chart_by_difficulty(runs: list[dict[str, Any]]) -> None:
    """EX and Soft F1 per difficulty — the overall score hides big gaps."""
    tags = [r["config"]["tag"] for r in runs]
    x = range(len(DIFFICULTIES))
    # Two bars per run per difficulty: EX solid, Soft F1 faded.
    width = 0.8 / max(2 * len(runs), 1)

    fig, ax = plt.subplots(figsize=(3.2 * len(runs) + 4, 4.4))
    colors = plt.get_cmap("tab10")

    for i, run in enumerate(runs):
        by_diff = run["summary"]["by_difficulty"]
        ex = [by_diff.get(d, {}).get("execution_accuracy", 0) for d in DIFFICULTIES]
        f1 = [by_diff.get(d, {}).get("soft_f1", 0) for d in DIFFICULTIES]
        color = colors(i)

        base = (2 * i - (2 * len(runs) - 1) / 2) * width
        b1 = ax.bar([p + base for p in x], ex, width, label=f"{tags[i]} · EX", color=color)
        b2 = ax.bar(
            [p + base + width for p in x],
            f1,
            width,
            label=f"{tags[i]} · Soft F1",
            color=color,
            alpha=0.45,
        )
        ax.bar_label(b1, fmt="%.2f", fontsize=7, padding=2)
        ax.bar_label(b2, fmt="%.2f", fontsize=7, padding=2)

    ax.set_xticks(list(x))
    ax.set_xticklabels(DIFFICULTIES)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Score")
    ax.set_title(f"Exactitude par difficulté ({_question_count(runs)} questions)")
    ax.legend(frameon=False, fontsize=8, ncol=len(runs))
    _style(ax)

    fig.tight_layout()
    fig.savefig(OUTPUT / "by_difficulty.png", dpi=150)
    plt.close(fig)


def chart_cost(runs: list[dict[str, Any]]) -> None:
    """Tokens per question against accuracy — the cost/quality tradeoff."""
    fig, ax = plt.subplots(figsize=(6.5, 4.6))

    for run in runs:
        c, s = run["config"], run["summary"]
        ax.scatter(
            s["tokens"]["prompt_per_question"],
            s["execution_accuracy"],
            s=120,
            color=ACCENT,
            zorder=3,
        )
        ax.annotate(
            c["tag"],
            (s["tokens"]["prompt_per_question"], s["execution_accuracy"]),
            textcoords="offset points",
            xytext=(0, 12),
            ha="center",
            fontsize=9,
        )

    ax.set_xlabel("Tokens d'entrée par question")
    ax.set_ylabel("Execution accuracy")
    ax.set_ylim(0, 1)
    ax.set_xlim(left=0)
    ax.set_title(f"Coût du prompt contre exactitude ({_question_count(runs)} questions)")
    _style(ax)
    ax.grid(alpha=0.25, linewidth=0.6)

    fig.tight_layout()
    fig.savefig(OUTPUT / "cost_vs_accuracy.png", dpi=150)
    plt.close(fig)


def analyse(tags: list[str] | None = None) -> None:

    runs = load_runs(tags)
    if not runs:
        raise SystemExit("aucun fichier evaluation-*.json dans reports/")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    table = print_table(runs)
    (OUTPUT / "comparison.md").write_text(table, encoding="utf-8")

    chart_accuracy(runs)
    chart_by_difficulty(runs)
    chart_cost(runs)

    print(f"{len(runs)} run(s) comparé(s). Sorties dans {OUTPUT}/")
