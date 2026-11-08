# Cave de Tibati — Version 2.8

## Confirmation d'envoi des commandes client

Après une transmission réussie au serveur, la page client affiche un écran de confirmation explicite :
- coche verte et message « Votre commande a bien été transmise ! » ;
- numéro de commande et nom de la table ;
- indication que la commande a été envoyée à la caisse ;
- rappel de conserver le numéro de commande.

Le bouton est désactivé pendant l'envoi pour éviter les doubles clics. Si la transmission échoue, le client reçoit un message d'erreur et peut réessayer. Un envoi vide est bloqué.

Le message confirme la réception par l'application et la transmission à la caisse ; il ne prétend pas que la commande a déjà été acceptée ou préparée.

## Déploiement

Remplacer les fichiers du projet par ceux de cette archive puis redéployer le service. Conserver les variables d'environnement et le disque persistant existants. Ne pas supprimer `/var/data/cave.db`.
