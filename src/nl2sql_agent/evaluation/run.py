"""Lance le benchmark. uv run python -m nl2sql_agent.evaluation.run --n 50"""

import argparse

from nl2sql_agent.evaluation import dataset
from nl2sql_agent.evaluation.runner import run
from nl2sql_agent.providers.factory import get_provider


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="nombre de questions")
    parser.add_argument("--quick", action="store_true", help="raccourci pour --n 30")
    parser.add_argument("--no-evidence", action="store_true")
    parser.add_argument("--max-tables", type=int, default=None)
    args = parser.parse_args()

    n = 30 if args.quick else args.n
    questions = dataset.sample(dataset.load(), n)
    print(f"{len(questions)} questions")

    _, summary, directory = run(
        questions,
        get_provider(),
        use_evidence=not args.no_evidence,
        max_tables=args.max_tables,
    )

    total_tokens = summary["prompt_tokens_total"] + summary["completion_tokens_total"]

    print("\n" + "-" * 42)
    print(f"Questions          : {summary['questions']}")
    print(f"Execution accuracy : {summary['execution_accuracy']} %")
    print(f"SQL valide         : {summary['valid_sql_rate']} %")
    print(f"Latence p50 / p95  : {summary['latency_p50_s']}s / {summary['latency_p95_s']}s")
    print(f"Tokens entree/q    : {summary['prompt_tokens_avg']}")
    print(f"Tokens total       : {total_tokens:,}")

    print("\nPar difficulte")
    for name, d in summary["by_difficulty"].items():
        print(f"  {name:<14} {d['correct']}/{d['total']}   {d['accuracy']} %")

    print("\nIssues")
    for name, count in sorted(summary["breakdown"].items()):
        print(f"  {name:<14} {count}")

    print(f"\nRapport : {directory}/report.md")


if __name__ == "__main__":
    main()
