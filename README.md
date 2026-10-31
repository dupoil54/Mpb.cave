# Cave de Tibati — application de gestion

## Fonctions incluses
- Catalogue et import initial des produits du classeur `gestion_cave.xlsx` (feuille Stock : code, désignation, catégorie, fournisseur, prix d’achat/vente, stock initial).
- Stocks, entrées/sorties/ajustements, seuils, alertes et ruptures.
- Tables illimitées, commandes individuelles par client et reçus en attente.
- Encaissement partiel/total et mise à crédit; suivi des ardoises et remboursements.
- Connexion employé par PIN, PIN stocké sous forme PBKDF2, journal d'activité.
- Lien client par table (`https://votre-domaine/?table=ID`) pour commander depuis le téléphone.

## Démarrage local
1. Installer Python 3.11+.
2. `python -m venv .venv` puis activer l’environnement.
3. `pip install -r requirements.txt`
4. `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Ouvrir `http://localhost:8000`.

Connexion initiale : PIN `1234`. Changez-le immédiatement : créez un compte admin dédié après le déploiement et retirez le PIN de démonstration dans la base avant usage réel. Le projet est un socle MVP; la gestion des rôles fins, la modification/suppression sécurisée des commandes, exports comptables, sauvegardes et durcissement anti-abus du menu public doivent être ajoutés avant exploitation commerciale critique.

## Déploiement public
Ce n'est pas un site statique : GitHub Pages/Netlify seuls ne peuvent pas exécuter l'API et la base SQLite. Déployez le dossier sur un hébergeur Python (Render, Railway ou VPS) avec disque persistant monté et `DATABASE_PATH` pointant vers ce disque. Commande de démarrage : `uvicorn main:app --host 0.0.0.0 --port $PORT`. Configurez HTTPS et sauvegardes automatiques. Plusieurs téléphones partagent alors la même base serveur.

## QR code / lien client
Créez une table dans l'interface, puis copiez son lien `https://votre-domaine/?table=ID`. Transformez ce lien en QR code et collez-le sur la table. Les commandes clients sont enregistrées comme commandes en attente et diminuent le stock dès leur création; l'équipe doit les valider/servir. Pour une exploitation réelle, ajoutez un statut de validation avant décrémentation du stock et une protection anti-spam par table.

## Données
Le fichier `products_seed.json` provient des lignes produits de la feuille `Stock` du classeur fourni. Le classeur original n'est pas modifié. Les autres feuilles (achats, ventes, rapports, personnel, avances, charges, bilan) ne sont pas encore migrées comme historiques transactionnels; les nouveaux flux de l'application constituent la source de vérité après mise en service.
