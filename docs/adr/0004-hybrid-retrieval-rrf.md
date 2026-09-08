# 0004 — Recherche hybride du schéma avec fusion RRF

**Statut :** accepté

## Contexte

Le dump BIRD charge les 11 bases dans un schéma unique : 75 tables issues de domaines sans
rapport — banque, chimie, Formule 1, forum de développeurs — cohabitent sans cloisonnement, avec
des identifiants opaques du type `A2` ou `frq_issd`.

Envoyer le schéma complet coûte cher, dégrade la précision par dilution, et ne passe pas à
l'échelle. Mais aucun signal de recherche ne suffit seul : le dense rate les correspondances
exactes d'identifiants, le lexical rate les reformulations.

## Décision

Rechercher avec les deux signaux, fusionner par Reciprocal Rank Fusion (`k=60`), reranker les 30
premiers avec un cross-encoder, puis étendre le long des clés étrangères.

Les valeurs `k=60` et top-30 sont des points de départ, pas des conclusions. L'ablation les
confirmera ou les corrigera.

## Conséquences

Chaque signal couvre le mode d'échec de l'autre.

RRF ne demande ni normalisation entre des échelles de score incomparables, ni réglage. C'est son
principal intérêt face à une pondération.

L'expansion par clés étrangères évite l'échec caractéristique où une jointure devient impossible
parce qu'un seul de ses deux côtés a été retenu.

La taille du prompt devrait chuter d'un ordre de grandeur — à mesurer.

En contrepartie : davantage de pièces mobiles, un second index à maintenir à jour, et le
reranking ajoute de la latence.

## Alternatives écartées

**Schéma complet dans le prompt** — conservé comme référence mesurée, pas écarté. Toute
affirmation sur l'apport de la recherche s'exprime comme un écart par rapport à elle.

**Dense seul** — échoue sur les questions qui citent un identifiant littéral.

**Pondération des scores** — impose de normaliser des distributions incomparables et de régler
un poids par jeu de données. RRF travaille sur les rangs et ne demande presque aucun paramètre.

## À revoir si

L'ablation montre qu'un signal n'apporte rien sur ces schémas — auquel cas il faut le retirer,
et le documenter.