# CAVE DE TIBATI — Application de gestion

## Modification apportée

L'ajout d'un produit au stock ne demande désormais **aucune photo** : il suffit de renseigner le libellé et la quantité initiale. La catégorie, le prix d'achat et le prix de vente restent disponibles. La modification du nom d'un article ne demande plus non plus de lien photo. Les catalogues affichent les articles sous forme de fiches textuelles, sans image.

## Contenu du projet

- `main.py` : serveur FastAPI et gestion de la base SQLite.
- `static/index.html` : interface de l'application.
- `requirements.txt` : dépendances Python pour l'installation et le déploiement.

## Installation locale

1. Installer Python 3.10 ou une version plus récente.
2. Ouvrir un terminal dans le dossier du projet.
3. Installer les dépendances :

   ```bash
   pip install -r requirements.txt
   ```

4. Démarrer le serveur :

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

5. Ouvrir `http://127.0.0.1:8000` dans le navigateur.

Premier accès administrateur : rôle Administrateur, PIN provisoire `1234`. Modifiez-le dès la première connexion.

## Déploiement sur Render

- Type : Web Service.
- Build command : `pip install -r requirements.txt`.
- Start command : `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Ajouter un disque persistant monté sur `/var/data`.
- Définir `DATABASE_PATH=/var/data/cave.db`.

Conservez le disque persistant existant lors d'un redéploiement afin de préserver les stocks, ventes, comptes et historiques.

## Fonctionnalités incluses

Gestion des produits et mouvements de stock, approvisionnement en gros, tables et reçus, commandes clients, encaissements, ardoises, employés et PIN, présences et salaires, charges, rapports, journal d'activité, sauvegarde et réinitialisation sécurisée des données.
