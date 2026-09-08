# Décisions d'architecture

Un fichier par décision : le contexte, ce qui a été retenu, les alternatives écartées et ce qui
ferait revenir dessus. Format [MADR](https://adr.github.io/madr/), légèrement adapté.

| # | Décision | Statut |
|---|---|---|
| [0001](0001-postgres-as-single-datastore.md) | PostgreSQL + pgvector comme unique base de données | Accepté |
| [0002](0002-langgraph-for-orchestration.md) | LangGraph pour l'orchestration | Accepté |
| [0003](0003-sqlglot-ast-validation.md) | Validation par AST avec sqlglot avant exécution | Accepté |
| [0004](0004-hybrid-retrieval-rrf.md) | Recherche hybride du schéma avec fusion RRF | Accepté |
| [0005](0005-provider-abstraction.md) | Abstraction des fournisseurs de modèles | Accepté |
| [0006](0006-eval-before-features.md) | Construire le harnais d'évaluation avant les fonctionnalités | Accepté |