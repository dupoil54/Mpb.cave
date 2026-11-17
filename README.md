# Cave de Tibati – version catalogue caisse + réinitialisation sécurisée

## Nouveautés
- Catalogue de produits en vignettes : nom, catégorie, prix et stock.
- Interface de prise de commande / caisse en vignettes.
- Migration SQLite non destructive : ajout de `products.image_url` uniquement si la colonne n'existe pas. Les tables et colonnes existantes sont conservées.
- Bouton « Vider toutes les données » visible uniquement pour l'administrateur, dans Ventes & bénéfices > Conservation des données.
- La réinitialisation crée automatiquement une sauvegarde avant suppression. Elle vide les produits/stocks, tables, commandes, lignes de vente, paiements, ardoises, mouvements, présences, charges et journal. Elle conserve les comptes employés, leurs PIN, les sessions, les paramètres et toute la structure SQL.

## Installation / déploiement
1. Remplacer les fichiers de l'application par ceux de cette archive.
2. Conserver le disque persistant Render monté sur `/var/data` et `DATABASE_PATH=/var/data/cave.db`.
3. Ne pas supprimer le fichier `cave.db` du disque persistant et ne pas recréer une base vide en production.
4. Redéployer le service. La migration ajoute automatiquement la colonne image sans effacer les données existantes.

## Photos (supprimées en v2.11) et chiffre d’affaires (tableau de bord)
L'application ne demande plus de photo ni de lien image : ni à la création d'un article, ni à la modification, ni dans la caisse. La colonne `products.image_url` reste dans la base (valeur vide) pour ne rien détruire ; elle n'est simplement plus utilisée.

## Réinitialiser les données
Se connecter avec le rôle Administrateur, ouvrir Ventes & bénéfices, puis la section Conservation des données. Cliquer sur « Vider toutes les données », saisir exactement `VIDER TOUT`, puis confirmer. Une sauvegarde `.db` est créée dans le dossier `backups` avant le nettoyage. Les accès administrateur et les comptes des employés sont conservés.

**Attention :** la réinitialisation est irréversible dans la base active. Télécharger et conserver la sauvegarde créée avant de poursuivre les opérations.


## Approvisionnement en stock de gros (v2.10)

Dans Gestion du stock, les profils Administrateur et Actionnaire peuvent enregistrer un achat par carton, pack ou caisse : article, nombre de colis, unités par colis et prix d'achat par colis. L'application calcule les unités entrantes, le coût total et le coût d'achat unitaire. Le coût unitaire du produit est ensuite actualisé par coût moyen pondéré (stock restant valorisé à l'ancien coût + nouvel achat), puis figé sur chaque nouvelle ligne de vente pour alimenter les rapports de coût et de bénéfice. L'historique des 100 derniers achats en gros est consultable dans la page Stock. La migration ajoute uniquement la table `stock_purchases` et ne supprime ni ne recrée les tables existantes.

## Tableau de bord
Le tableau de bord affiche le chiffre d’affaires du jour, du mois et de l’année (commandes payées ou à crédit, comme dans les rapports). Visible par l’administrateur et l’actionnaire.

## Version 2.14
- Tableau de bord : valeur du stock au prix d’achat et au prix de vente potentiel.
- Ventes & bénéfices : ligne « Bénéfice réalisé sur les sommes encaissées » (au prorata de la marge de chaque reçu), totaux par groupe (Vins & spiritueux / Bières, jus & eau) et catégories cliquables pour voir le détail des produits vendus.
- Stock : mouvements sélectionnés par catégorie puis par article ; marge bénéficiaire (%) sur chaque carte d’article.
- Caisse : peut corriger un reçu payé (hors reçus liés à une ardoise).
- Ardoises : la facture d’origine s’affiche dans la fenêtre de règlement.
