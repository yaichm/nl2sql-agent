# 0006 — Construire le harnais d'évaluation avant les fonctionnalités

**Statut :** accepté

## Contexte

L'ordre naturel serait de construire la recherche, puis l'agent, puis de mesurer. Il produit un
système dont la précision est inconnue, dont on ne peut attribuer les résultats à aucun
composant, et dont les améliorations sont affirmées plutôt que démontrées.

## Décision

L'ordre est : version naïve d'abord, puis le harnais d'évaluation, puis chaque fonctionnalité —
intégrée uniquement accompagnée de l'écart qu'elle a produit.

## Conséquences

Chaque fonctionnalité est justifiée par un chiffre. Les régressions sont détectées par la CI
plutôt que par un utilisateur. Ce qui n'améliore rien est retiré au lieu de s'accumuler.

Le tableau de résultats s'écrit comme sous-produit du travail, sans effort de rédaction en fin
de projet.

En contrepartie : un délai avant que quoi que ce soit ne paraisse impressionnant, et
l'obligation de figer le benchmark et les définitions de métriques tôt, au moment où on les
comprend le moins bien.

## Ce que l'évaluation ne dira pas

Le benchmark BIRD contient des erreurs d'annotation documentées. Une part des requêtes de
référence est incorrecte ou repose sur des conventions discutables — par exemple la question
1473, dont la référence divise une moyenne mensuelle par douze alors que la colonne contient
déjà des valeurs mensuelles.

Le plafond atteignable n'est donc pas 100 %. À titre de repère, la performance humaine mesurée
sur le jeu complet est de 92,96 %.

Conséquence pratique : une analyse manuelle d'un échantillon d'échecs fait partie du travail, et
les cas où le système avait raison contre la référence sont à documenter plutôt qu'à corriger.

## Alternatives écartées

**Mesurer à la fin** — le comportement par défaut, et la raison pour laquelle la plupart des
projets text-to-SQL ne publient aucun chiffre.

**Vérification à l'œil sur quelques questions** — insensible aux mouvements de deux à cinq
points que produisent réellement les fonctionnalités individuelles.

## À revoir si

Rien. C'est le principe qui structure tout le reste du projet.