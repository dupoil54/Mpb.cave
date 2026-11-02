# Cave de Tibati — gestion intégrée

## Fonctions de cette version

### Connexion et droits
- Page d'accueil avec choix du poste : Administrateur, Actionnaire, Service ou Caisse.
- Chaque employé possède son propre compte et son PIN initial.
- Le PIN initial doit être changé à la première connexion ; le PIN est stocké sous forme PBKDF2.
- Création et gestion des employés par l'administrateur et l'actionnaire. Seul l'administrateur peut créer un autre compte administrateur.
- Les droits sont contrôlés par l'API : Service = tables et reçus ; Caisse = ardoises, tables/reçus et journal ; Administrateur et Actionnaire = gestion complète.

### Exploitation
- Articles et stock saisis manuellement, sans catalogue préchargé.
- Seuls l'administrateur et l'actionnaire peuvent consulter/modifier le stock, les articles et les prix.
- Tables, commandes individuelles, reçus en attente et modification d'un reçu avant tout paiement.
- Les commandes envoyées par les clients via le lien de leur table apparaissent dans Tables & reçus du profil Caisse.
- Encaissement, ardoises et journal d'activité.
- Présences enregistrées et approuvées par l'administrateur ou l'actionnaire ; salaires mensuels fixes avec déduction au prorata des jours calendaires pour les absences approuvées.
- Saisie des charges et rapports de ventes, coût des marchandises, bénéfice brut estimé et bénéfice net estimé par jour, semaine, mois ou année.
- Les indicateurs du tableau de bord sont cliquables et ouvrent la rubrique concernée.

## Premier démarrage

1. Installer Python 3.11 ou plus récent.
2. `python -m venv .venv` puis activer l'environnement.
3. `pip install -r requirements.txt`
4. `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Ouvrir `http://localhost:8000`.

Le premier compte est Administrateur avec le PIN provisoire `1234`. À la première connexion, il faut obligatoirement le remplacer. Créez ensuite les autres employés depuis Employés et communiquez à chacun son poste et son PIN initial.

## Déploiement cloud

Cette version utilise SQLite. Pour partager les mêmes données entre les téléphones, l'application doit être hébergée sur un serveur Python et la base doit résider sur un **disque persistant** du fournisseur cloud. Exemple Render : créer un Web Service Python, définir la commande de démarrage `uvicorn main:app --host 0.0.0.0 --port $PORT`, ajouter un disque persistant (par exemple monté sur `/var/data`) et définir `DATABASE_PATH=/var/data/cave.db`.

Ne pas déployer cette application comme simple site statique sur GitHub Pages ou Netlify : ils n'exécutent pas cette API Python. Un seul service applicatif doit écrire dans cette base SQLite ; pour plusieurs instances ou une forte montée en charge, il faudra migrer la couche de données vers PostgreSQL. Prévoir des sauvegardes régulières du disque et tester leur restauration.

## Stock vide et migration

Lors de la première exécution de cette version sur une base existante, tous les articles déjà présents sont archivés et leur quantité mise à zéro. Les anciennes lignes restent en base afin de préserver les références des reçus historiques. Cette migration ne se produit qu'une seule fois. Les nouveaux articles saisis ensuite ne sont pas effacés au redémarrage.

## Lien client

Créer une table, puis utiliser le lien `https://votre-domaine/?table=ID` associé à cette table. Il peut être converti en QR code et affiché sur la table. Les commandes web apparaissent dans la liste des reçus de l'espace Caisse.

## Règles et limites à connaître

- Le stock est actuellement décrémenté au moment où une commande est créée, y compris pour une commande web, et non lors de sa validation par la caisse.
- Le rapport de ventes se base sur les paiements encaissés pendant la période. Le coût des marchandises est estimé à partir du coût d'achat enregistré sur les lignes de commande ; les charges sont celles saisies dans le module Charges. Il faut donc maintenir les prix d'achat et les charges à jour.
- La déduction des absences est calculée en divisant le salaire mensuel par le nombre de jours calendaires du mois. Cette règle doit être adaptée si les contrats de la Cave utilisent une autre base de calcul.
- Le lien client public n'a pas encore de système anti-spam ni d'étape de validation de commande avant décrémentation du stock.
- L'impression actuelle ouvre la boîte d'impression du navigateur. L'impression Bluetooth directe nécessite une intégration supplémentaire selon le modèle d'imprimante et le navigateur/appareil utilisé.
- Avant mise en production : remplacer le PIN provisoire, vérifier les rôles avec des comptes de test, activer HTTPS, sécuriser les sauvegardes et protéger l'accès à l'hébergeur.
