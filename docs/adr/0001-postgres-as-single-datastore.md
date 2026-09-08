# 0001 — PostgreSQL + pgvector comme unique base de données

**Statut :** accepté

## Contexte

Trois besoins de stockage : les données métier interrogées, un index vectoriel sur le catalogue
de schéma, un index lexical sur ce même catalogue.

Le réflexe habituel serait une base vectorielle dédiée et un moteur de recherche, à côté de
Postgres.

## Décision

Une seule instance PostgreSQL pour les trois. `pgvector` avec index HNSW pour la recherche
dense, `tsvector` / `ts_rank` natifs pour la recherche lexicale.

## Conséquences

Une connexion, une sauvegarde, une seule migration à gérer. Les filtres de recherche peuvent
joindre directement les métadonnées du catalogue — avec un store séparé il faudrait dupliquer
ces métadonnées ou faire un second aller-retour.

`docker compose up` démarre un service au lieu de trois, ce qui compte pour quiconque veut
essayer le projet.

La contrainte est aussi matérielle. La machine de développement dispose d'environ 3 Go de RAM
disponible ; faire tourner Postgres, une base vectorielle et un moteur de recherche en parallèle
n'est pas envisageable. Postgres consomme quelques centaines de mégaoctets au repos alors qu'il
sert 2 Go de données sur disque — il ne charge en mémoire que les pages dont il a besoin.

En contrepartie : le réglage de la recherche vectorielle est plus grossier que sur Qdrant, pas
de quantification native, et faire monter la charge vectorielle revient à faire monter toute la
base.

Le catalogue tient dans l'ordre du millier d'entrées — 75 tables et leurs colonnes. À cette
échelle, ce n'est pas pgvector le goulot d'étranglement, c'est l'appel au LLM.

## Alternatives écartées

**Qdrant, Weaviate** — meilleures fonctionnalités vectorielles, pensées pour des millions de
vecteurs. Le coût opérationnel est réel, le bénéfice ne l'est pas ici.

**Elasticsearch pour le BM25** — bonne implémentation, mais un cluster de plus à faire tourner
pour un signal de classement que la recherche plein texte de Postgres rend correctement à cette
échelle.

## À revoir si

Le catalogue dépasse le million de vecteurs, ou si le rappel plafonne et que l'ablation montre
que c'est l'index vectoriel qui limite, et non le reranker.