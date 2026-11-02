# Cave de Tibati — application de gestion

## Fonctions incluses
- Gestion des stocks sans aucun produit préenregistré : le gérant crée lui-même chaque article.
- Création d'un article avec libellé et quantité initiale obligatoires ; catégorie, prix d'achat et prix de vente facultatifs.
- Code article généré automatiquement si aucun code n'est fourni.
- Entrées, sorties, ajustements, seuils et alertes de stock.
- Renommage et archivage des articles sans effacer les anciennes lignes de reçus.
- Tables sans limite applicative, commandes individuelles par client et reçus en attente.
- Encaissement partiel/total et mise à crédit; suivi des ardoises et remboursements.
- Connexion employé par PIN, PIN stocké sous forme PBKDF2, journal d'activité.
- Lien client par table (`https://votre-domaine/?table=ID`) pour commander depuis le téléphone.

## Démarrage local
1. Installer Python 3.11+.
2. `python -m venv .venv` puis activer l’environnement.
3. `pip install -r requirements.txt`
4. `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Ouvrir `http://localhost:8000`.

Connexion initiale : PIN `1234`. Changez-le immédiatement avant l'exploitation réelle.

## Déploiement public
Ce n'est pas un site statique : GitHub Pages/Netlify seuls ne peuvent pas exécuter l'API et la base SQLite. Déployez le dossier sur un hébergeur Python (Render, Railway ou VPS) avec disque persistant monté et `DATABASE_PATH` pointant vers ce disque. Commande de démarrage : `uvicorn main:app --host 0.0.0.0 --port $PORT`. Configurez HTTPS et sauvegardes automatiques. Plusieurs téléphones partagent alors la même base serveur.

## Stock vide et migration
Aucun fichier d'import ni catalogue de démonstration n'est chargé au démarrage. Lors de la première exécution de cette version sur une base existante, les anciens articles préchargés sont désactivés et leur quantité est mise à zéro ; ils restent archivés en base pour préserver les anciennes références de reçus. Cette opération est exécutée une seule fois grâce à un marqueur de migration. Les articles ajoutés ensuite restent disponibles après les redémarrages.

Dans **Stocks > Enregistrer un nouvel article**, saisissez le libellé et la quantité initiale. La catégorie et les prix sont facultatifs. Le code est généré automatiquement. Les quantités initiales sont inscrites dans l'historique des mouvements.

## QR code / lien client
Créez une table dans l'interface, puis copiez son lien `https://votre-domaine/?table=ID`. Transformez ce lien en QR code et collez-le sur la table. Les commandes clients sont enregistrées comme commandes en attente et diminuent le stock dès leur création. Pour une exploitation réelle, ajoutez une protection anti-abus du menu public et un mécanisme de validation avant consommation du stock.

## Sécurité et limites
Le projet reste un socle MVP. Avant un usage commercial critique, prévoyez notamment le changement du PIN provisoire, des sauvegardes testées, une gestion détaillée des rôles, la validation des commandes client, des tests de charge et une vérification de la configuration du disque persistant.
