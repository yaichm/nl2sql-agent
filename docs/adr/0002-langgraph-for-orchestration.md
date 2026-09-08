# 0002 — LangGraph pour l'orchestration

**Statut :** accepté

## Contexte

Le flux de contrôle contient des cycles. Une validation qui échoue renvoie vers la génération.
Une erreur d'exécution aussi. Une requête coûteuse met le traitement en pause en attendant une
confirmation humaine.

Il faut également que l'état soit inspectable, parce que la question quotidienne pendant le
développement sera « pourquoi a-t-il choisi cette table ».

## Décision

LangGraph, avec un état déclaré en `TypedDict` et des nœuds nommés.

## Conséquences

Les cycles sont exprimés directement, plutôt qu'avec une boucle `while` enroulée autour d'une
chaîne d'appels.

Le checkpointing donne deux choses gratuitement : la mémoire conversationnelle pour les
questions de suivi, et la possibilité de rejouer une exécution ratée depuis n'importe quel
nœud. La primitive `interrupt` permet d'implémenter la confirmation humaine dans le graphe
plutôt que dans l'interface — la supervision fait partie du système, pas de l'affichage.

Le graphe se dessine, ce qui rend l'architecture explicable sans lire le code.

En contrepartie : une dépendance à une API qui bouge vite, et plus de cérémonie qu'une simple
fonction pour le chemin nominal.

## Alternatives écartées

**Python simple** — parfaitement viable, et à reconsidérer si le graphe reste petit. Écarté
pour le checkpointing et l'interruption, qu'il faudrait réécrire.

**CrewAI, AutoGen** — pensés pour des agents multiples aux rôles distincts. Le problème traité
ici est un agent unique, avec un enchaînement déterministe et deux arêtes de reprise. Ces
abstractions ajoutent de l'indirection sans rien résoudre.

**Chaînes LangChain seules** — pas de cycles, ce qui est précisément le besoin.

## À revoir si

Le graphe se stabilise à quatre ou cinq nœuds sans reprise réelle. Dans ce cas, Python simple
suffirait et la dépendance ne se justifierait plus.