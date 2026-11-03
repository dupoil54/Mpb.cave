# Cave de Tibati — Version 2.1 : données persistantes et coûts par catégorie

## Correctifs apportés

- Les données métier (articles, quantités, tables, reçus, paiements, ardoises, journal, employés, présences, salaires et charges) sont enregistrées dans une base SQLite située sur le stockage configuré côté serveur. La déconnexion ne supprime que le jeton de session ; elle ne vide jamais la base.
- En production Render, l'application refuse désormais de démarrer si la base n'est pas placée sur `/var/data` (disque persistant) : cela évite de fonctionner silencieusement sur le disque temporaire du conteneur.
- SQLite utilise WAL, synchronisation renforcée et délai d'attente pour améliorer la fiabilité des écritures.
- Une sauvegarde manuelle de la base peut être déclenchée par l'administrateur ou l'actionnaire depuis **Ventes & bénéfices**.
- Les rapports présentent maintenant, pour chaque catégorie, les quantités vendues, le chiffre d'affaires, le coût d'achat et le bénéfice brut.
- La catégorie de chaque ligne de commande est conservée au moment de la vente. Une modification ultérieure de la catégorie de l'article ne modifie donc pas les anciens rapports. Les anciennes lignes sont migrées automatiquement au démarrage.

## IMPORTANT — configuration Render obligatoire

Le disque local normal d'un Web Service Render est éphémère. Une base enregistrée dans le dossier du code peut donc disparaître lors d'un redéploiement, d'un remplacement d'instance ou d'un redémarrage. La déconnexion seule ne doit pas effacer les données ; le problème est généralement le chemin de stockage ou l'absence de disque persistant.

1. Ouvrir le service Web de Cave de Tibati dans Render.
2. Ajouter un **Persistent Disk** (disque persistant), par exemple avec le point de montage `/var/data`.
3. Dans **Environment**, définir exactement `DATABASE_PATH` = `/var/data/cave.db`.
4. Garder une seule instance applicative avec SQLite. Ne pas lancer plusieurs instances/replicas qui écrivent chacune dans un fichier SQLite différent.
5. Redéployer le service.
6. Se connecter comme administrateur ou actionnaire, ouvrir **Ventes & bénéfices** et vérifier que la rubrique **Conservation des données** indique « Stockage persistant détecté (/var/data) ».
7. Créer une sauvegarde depuis le même écran après chaque opération importante, et mettre en place une copie externe régulière du fichier de sauvegarde. Une sauvegarde conservée uniquement sur le même disque ne protège pas contre la perte de ce disque.

**Ne pas déployer cette application sur GitHub Pages ou Netlify comme site statique** : elle nécessite un serveur Python. Utiliser le Web Service Python Render.

## Préserver les données actuellement présentes

Avant de modifier le point de montage ou de redéployer, si des données existent encore dans l'instance actuelle, il faut copier l'ancienne base `cave.db` vers `/var/data/cave.db` avant de relancer l'application. Ne pas créer une base vide à la place de l'ancienne. Si l'ancien service a déjà été redémarré sans disque persistant et que son stockage temporaire a été supprimé, les données perdues ne peuvent pas être reconstituées par ce correctif ; restaurer alors la dernière sauvegarde disponible.

## Installation / démarrage local

```bash
python -m venv .venv
# activer l'environnement virtuel
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

En local, la base par défaut est `cave.db` à côté de `main.py`. Pour choisir un autre emplacement, définir `DATABASE_PATH` avant le démarrage.

## Sécurité et conservation à long terme

- Le compte administrateur initial utilise le PIN provisoire `1234` ; il faut le changer dès la première connexion.
- Ne jamais supprimer le disque persistant ni remplacer la base par un fichier vide.
- Les articles peuvent être archivés ; les ventes et mouvements historiques restent dans la base.
- Les sauvegardes doivent être copiées régulièrement hors du serveur et leur restauration doit être testée.
- Pour plusieurs instances simultanées, plusieurs points de vente ou un volume important, migrer vers PostgreSQL géré plutôt que partager un fichier SQLite.

## Rapports

Les périodes disponibles restent : jour, semaine, mois et année. Le tableau « Coût des produits vendus par catégorie » s'appuie sur le coût d'achat enregistré dans chaque ligne de vente. Pour obtenir des marges fiables, renseigner le prix d'achat des articles et tenir à jour les charges.
