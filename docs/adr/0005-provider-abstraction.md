# 0005 — Abstraction des fournisseurs de modèles

**Statut :** accepté

## Contexte

L'évaluation rejoue le benchmark des dizaines de fois, ce qui a un coût. Le budget API est
limité à un mois : le projet doit continuer de fonctionner ensuite.

Par ailleurs, une part significative des déploiements européens ne peut pas envoyer de schéma ni
de contenu de requête vers une API hébergée hors UE.

## Décision

Une interface `LLMProvider` unique, avec deux implémentations sélectionnées par variable
d'environnement : Mistral pour le développement et l'évaluation, Ollama pour l'exécution locale.

Un troisième fournisseur — Azure OpenAI, Bedrock, Vertex — s'ajouterait en une trentaine de
lignes, puisqu'ils exposent tous une API de complétion comparable. Il n'est pas implémenté parce
qu'il ne démontrerait rien de plus : c'est le couple API distante / modèle local qui met
l'abstraction à l'épreuve, avec des différences réelles d'authentification, de latence et de
capacité.

## Conséquences

Le choix du modèle devient une expérience mesurée plutôt qu'une hypothèse. Le tableau de
résultats affiche l'arbitrage explicitement.

Un chemin entièrement local existe, pour les déploiements sous contrainte de souveraineté comme
pour faire tourner le projet à coût marginal nul.

Aucun verrouillage sur les particularités du SDK d'un fournisseur.

En contrepartie : l'interface se limite à l'intersection de ce que les deux supportent, donc
toute fonctionnalité spécifique demandera une échappatoire explicite.

Et il faut s'attendre à un écart de qualité important. La machine de développement dispose
d'environ 3 Go de RAM : seul un modèle de 1,5 à 3 milliards de paramètres y tient. À titre de
repère, le classement BIRD Mini-Dev en PostgreSQL donne 18,40 % à Llama3-8B et 12,40 % à
Mixtral-8x7B, contre 35,80 % à GPT-4. Un modèle local de cette taille produira donc un score
faible. Le publier tel quel fait partie du résultat : la souveraineté a un coût, et il se mesure.

## Alternatives écartées

**Un seul fournisseur** — plus simple, mais ferme à la fois l'argument du coût et celui de la
souveraineté.

**LiteLLM** — réponse toute faite et raisonnable. Écartée parce que l'interface nécessaire ici
est étroite, et que l'écrire rend le comptage des tokens et la politique de reprise explicites
plutôt qu'hérités.

## À revoir si

Une offre d'emploi ou un contexte client précis rend un fournisseur particulier pertinent.
L'ajout est alors trivial et se justifie par le besoin, pas par l'exhaustivité.