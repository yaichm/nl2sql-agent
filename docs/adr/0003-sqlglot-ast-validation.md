# 0003 — Validation par AST avec sqlglot avant exécution

**Statut :** accepté

## Contexte

Le SQL généré échoue de trois manières : il ne se parse pas, il référence des identifiants qui
n'existent pas, ou il fait quelque chose qui devrait être interdit.

Les trois doivent être détectés avant que la requête n'atteigne la base. Le troisième cas pour
des raisons de sécurité. Les deux premiers parce que l'erreur est bien plus exploitable comme
retour structuré vers le nœud de réparation que comme exception remontée par PostgreSQL.

## Décision

Parser chaque requête générée avec sqlglot et faire porter les vérifications sur l'arbre
syntaxique. Valider les identifiants contre le catalogue de schéma. Rejeter tout ce dont la
racine n'est pas un `SELECT`, ou qui contient une écriture n'importe où dans l'arbre.

## Conséquences

Les noms de tables et de colonnes inventés — le mode d'échec dominant — sont détectés de façon
déterministe, et réparés avec une suggestion précise plutôt qu'avec un nouvel essai à l'aveugle.

Une écriture dissimulée dans une CTE ou une sous-requête est détectée, ce qu'une recherche
textuelle ne fait pas.

La validation coûte quelques millisecondes, à comparer aux secondes que prend l'appel au modèle.
Elle est donc gratuite en pratique.

En contrepartie : le catalogue doit rester synchronisé avec la base, sinon des requêtes valides
sont rejetées. Et la couverture dialectale de sqlglot reste imparfaite sur les syntaxes exotiques.

Un point découvert au chargement des données : PostgreSQL a créé les colonnes en minuscules
(`consumption`, pas `Consumption`). La comparaison des identifiants doit donc se faire sans
tenir compte de la casse, sous peine de rejeter des requêtes correctes.

## Alternatives écartées

**Expressions régulières, liste de mots interdits** — mises en échec par les commentaires, la
casse, les littéraux et l'imbrication. Ce n'est pas un contrôle de sécurité.

**`EXPLAIN` seul** — détecte la syntaxe et les identifiants inconnus, mais exige un aller-retour
vers la base et n'offre aucune couche de politique.

**Se reposer sur le rôle en lecture seule uniquement** — nécessaire mais pas suffisant. Il ne
fournit aucun retour structuré pour la réparation, et la défense en profondeur suppose plusieurs
couches indépendantes.

## À revoir si

La synchronisation du catalogue devient une source d'échecs plus fréquente que les identifiants
inventés qu'elle permet de détecter.