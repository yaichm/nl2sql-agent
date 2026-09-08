# NL→SQL Agentic Data Assistant

Un assistant qui répond à des questions métier en écrivant et en exécutant du SQL sur PostgreSQL.

En cours de développement.

## Le problème

La plupart des démos text-to-SQL tournent sur des schémas jouets : cinq tables, tout le schéma
collé dans le prompt, aucune évaluation.

Ici la base contient 75 tables issues de 11 domaines sans rapport — banque tchèque, chimie,
Formule 1, forum de développeurs, dossiers médicaux — chargées dans un schéma unique, sans
cloisonnement. Avec des colonnes nommées `A2` ou `frq_issd`, et des dates stockées en texte au
format `201308`. Trop gros pour être collé dans un prompt, et incompréhensible pour un modèle
qui n'a que les noms de colonnes.

## L'approche

Récupérer le schéma au lieu de le coller. Chaque table et chaque colonne est indexée avec une
description en langage naturel générée à partir de son contenu ; seules les tables pertinentes
partent dans le prompt. La recherche combine similarité vectorielle (pgvector) et recherche
lexicale (`tsvector`).

Valider avant d'exécuter. Le SQL généré est parsé avec sqlglot et vérifié contre le catalogue
réel de la base. Les identifiants inventés sont l'erreur la plus fréquente et se détectent de
façon déterministe. Une couche de garde-fous refuse ensuite tout ce qui n'est pas un `SELECT`,
et l'exécution se fait avec un rôle PostgreSQL en lecture seule.

Mesurer. Une version naïve sert de référence, et chaque amélioration est comparée à elle sur un
benchmark public.

## Stack

LangGraph pour l'orchestration. PostgreSQL 16 avec pgvector, qui sert à la fois de base et
d'index vectoriel. Un modèle d'embedding exécuté en local. Mistral ou Ollama pour la génération,
derrière une interface commune. sqlglot pour la validation. Langfuse pour l'observabilité.
FastAPI et Streamlit pour l'exposition.

## Évaluation

Benchmark BIRD Mini-Dev, dialecte PostgreSQL : 500 questions avec leur requête de référence.
La métrique principale est l'*execution accuracy* — on compare les résultats retournés, pas le
texte des requêtes.

Points de repère publiés sur ce même jeu : GPT-4 seul atteint 35,80 %, TA-SQL avec le même
GPT-4 atteint 50,80 %, le meilleur système publié 65,80 %. L'écart entre les deux premiers
mesure ce qu'apporte une architecture de sélection de schéma, à modèle constant.

## Documentation

[`ARCHITECTURE.md`](ARCHITECTURE.md) pour la conception technique, [`docs/adr/`](docs/adr/) pour
les décisions et les alternatives écartées, [`ROADMAP.md`](ROADMAP.md) pour les étapes.

## Lancer

```bash
cp .env.example .env
make install
docker compose up -d
make check
```

## Données

Ce projet utilise le benchmark BIRD Mini-Dev, publié sous licence CC BY-SA 4.0. Les données ne
sont pas redistribuées ; elles se téléchargent depuis la source officielle.

Li et al., *Can LLM Already Serve as a Database Interface? A Big Bench for Large-Scale Database
Grounded Text-to-SQLs*, NeurIPS 2023 — https://bird-bench.github.io/