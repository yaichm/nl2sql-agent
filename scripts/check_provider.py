"""Vérifie que le fournisseur répond. uv run python -m scripts.check_provider"""

from nl2sql_agent.providers.factory import get_provider


def main() -> None:
    provider = get_provider()
    print(f"Fournisseur : {provider.name} / {provider.model}")

    result = provider.complete(
        system="Tu réponds uniquement par du SQL, sans commentaire ni balise.",
        user="Compte les lignes de la table yearmonth.",
    )

    print(f"\n{result.text}")
    print(
        f"\n{result.prompt_tokens} tokens entrée, "
        f"{result.completion_tokens} sortie, "
        f"{result.latency_s:.2f}s"
    )


if __name__ == "__main__":
    main()