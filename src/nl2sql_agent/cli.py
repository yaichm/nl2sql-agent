"""Single entry point for the project.

uv run nl2sql describe                        # generate table descriptions
uv run nl2sql index                           # build the search index
uv run nl2sql search "how much did customer 6 consume"
uv run nl2sql validate --last hybrid          # diagnostic, no API call
uv run nl2sql run --mode baseline --n 50
uv run nl2sql run --mode hybrid --n 50
uv run nl2sql run --mode agent --n 50         # retrieval + repair loop
uv run nl2sql eval --last baseline
uv run nl2sql analyse
"""

import argparse
from pathlib import Path

from nl2sql_agent.catalog.db import admin_connection
from nl2sql_agent.catalog.introspect import introspect
from nl2sql_agent.evaluation import analyse, dataset, evaluate, generate
from nl2sql_agent.providers.factory import get_provider
from nl2sql_agent.retrieval import check as check_module
from nl2sql_agent.retrieval import describe
from nl2sql_agent.retrieval import index as index_module
from nl2sql_agent.retrieval import search as search_module
from nl2sql_agent.retrieval import selector as selector_module
from nl2sql_agent.retrieval.validate import Catalog

REPORTS = Path("reports")


def latest_predictions(tag: str) -> Path:
    """Most recent predictions file for a given tag."""
    candidates = sorted((REPORTS / tag).glob("predictions-*.json"))
    if not candidates:
        raise SystemExit(f"aucune prédiction dans reports/{tag}/")
    return candidates[-1]


def do_describe(args: argparse.Namespace) -> None:
    with admin_connection() as conn:
        tables = introspect(conn)

    descriptions = describe.describe_tables(tables, get_provider(), refresh=args.refresh)
    print(f"\n{len(descriptions)} descriptions dans {describe.CACHE}")

    name, text = next(iter(descriptions.items()))
    print(f"\nExemple — {name} :\n{text}")


def do_index(args: argparse.Namespace) -> None:
    descriptions = describe.load_descriptions()
    if not descriptions:
        raise SystemExit("aucune description : lance d'abord `nl2sql describe`")

    with admin_connection() as conn:
        tables = introspect(conn)
        count = index_module.build(conn, tables, descriptions)

    print(f"{count} tables indexées dans {index_module.SCHEMA}.tables")


def do_search(args: argparse.Namespace) -> None:
    with admin_connection() as conn:
        hits = search_module.search(conn, args.question, top_k=args.top_k)

    print(f"« {args.question} »\n")
    print(f"{'table':<28} {'score':>8}  {'dense':>5} {'lex':>5}")
    for hit in hits:
        dense = hit.dense_rank if hit.dense_rank else "-"
        lex = hit.lexical_rank if hit.lexical_rank else "-"
        print(f"{hit.name:<28} {hit.score:>8.5f}  {dense:>5} {lex:>5}")


def do_validate(args: argparse.Namespace) -> None:
    path = Path(args.predictions) if args.predictions else latest_predictions(args.last)
    with admin_connection() as conn:
        result = check_module.check_predictions(conn, path)
    check_module.report(result)


def do_generate(args: argparse.Namespace) -> Path:
    questions = dataset.sample(dataset.load(), args.n, seed=args.seed)

    with admin_connection() as conn:
        tables = introspect(conn)
        selector = selector_module.build(args.mode, tables, conn=conn, top_k=args.top_k)
        agent = args.mode == "agent"

        return generate.generate(
            questions,
            selector,
            get_provider(),
            tag=args.tag or args.mode,
            use_evidence=not args.no_evidence,
            agent=agent,
            catalog=Catalog(tables) if agent else None,
            max_attempts=args.max_attempts,
        )


def do_eval(args: argparse.Namespace) -> None:
    path = Path(args.predictions) if args.predictions else latest_predictions(args.last)
    evaluate.evaluate_file(path)


def add_generation_args(parser: argparse.ArgumentParser) -> None:
    """Options shared by generate and run."""
    parser.add_argument("--mode", choices=("baseline", "hybrid", "agent"), default="baseline")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument(
        "--seed", type=int, default=42, help="change l'échantillon ; garder fixe pour comparer"
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="tables retenues en mode hybrid et agent"
    )
    parser.add_argument(
        "--max-attempts", type=int, default=3, help="réparations maximum en mode agent"
    )
    parser.add_argument("--tag", default=None, help="nom du dossier, par défaut le mode")
    parser.add_argument("--no-evidence", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(prog="nl2sql")
    sub = parser.add_subparsers(dest="command", required=True)

    desc = sub.add_parser("describe", help="générer les descriptions de tables")
    desc.add_argument("--refresh", action="store_true", help="regénérer même si le cache existe")

    sub.add_parser("index", help="construire l'index de recherche")

    srch = sub.add_parser("search", help="tester la recherche sur une question")
    srch.add_argument("question")
    srch.add_argument("--top-k", type=int, default=10)

    val = sub.add_parser("validate", help="diagnostiquer la validation sur des prédictions")
    val.add_argument("predictions", nargs="?", default=None)
    val.add_argument("--last", default=None)

    add_generation_args(sub.add_parser("generate", help="générer les prédictions"))

    ev = sub.add_parser("eval", help="évaluer un fichier de prédictions")
    ev.add_argument("predictions", nargs="?", default=None)
    ev.add_argument("--last", default=None, help="évaluer le dernier run d'un tag")

    add_generation_args(sub.add_parser("run", help="générer puis évaluer"))

    ana = sub.add_parser("analyse", help="comparer les runs et tracer les graphiques")
    ana.add_argument("--tags", nargs="*", default=None)

    args = parser.parse_args()

    if args.command == "describe":
        do_describe(args)
    elif args.command == "index":
        do_index(args)
    elif args.command == "search":
        do_search(args)
    elif args.command == "validate":
        if not args.predictions and not args.last:
            raise SystemExit("précise un fichier, ou --last <tag>")
        do_validate(args)
    elif args.command == "generate":
        do_generate(args)
    elif args.command == "eval":
        if not args.predictions and not args.last:
            raise SystemExit("précise un fichier, ou --last <tag>")
        do_eval(args)
    elif args.command == "run":
        path = do_generate(args)
        print()
        evaluate.evaluate_file(path)
    elif args.command == "analyse":
        analyse.analyse(args.tags)


if __name__ == "__main__":
    main()
