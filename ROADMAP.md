# Roadmap de réimplémentation

## Objectif

Réimplémenter GuardianAngel avec une architecture compatible avec `asyncio`,
afin de surveiller les parapentistes via PureTrack et de communiquer avec les
superviseurs et les parapentistes via Discord.

## Réalisé

- [x] Boucle de monitoring compatible avec `asyncio`.
- [x] Appels PureTrack bloquants exécutés hors de la boucle asyncio.
- [x] Envoi de notifications dans le canal Discord général.
- [x] Notification du démarrage et de l'arrêt de la surveillance dans Discord.
- [x] Envoi optionnel du même message en DM au parapentiste.
- [x] Réception des réponses texte et des réactions Discord.
- [x] Gestion des réactions avec et sans message présent dans le cache Discord.
- [x] Association d'une réponse à la clé PureTrack du message concerné.
- [x] Gestion de plusieurs parapentistes partageant le même `discord_id`.
- [x] Machine d'état avec les états `Unknown`, `Flying`, `Clearance`, `Alert`,
	`Landed` et `Disconnected`.
- [x] Capture optionnelle des réponses brutes PureTrack.
- [x] Replay des événements capturés sans accès réseau.
- [x] Mode replay `dry-run` sans notification Discord.
- [x] Nettoyage des tâches asyncio et des timers de la machine d'état.
- [x] Tests de régression et tests d'intégration hors réseau.
- [x] Configuration exemple sans données sensibles.
- [x] Reprendre sans clearance un pilote déjà posé après un redémarrage.
- [x] Restaurer de façon sûre un état de vol ou une perte de signal après un crash.
- [x] Maintenir le diagramme PlantUML du README synchronisé avec l'automate.

## Prochaines étapes prioritaires

### 1. Algorithme de détection

- [ ] Définir les règles métier pour distinguer vol, marche, auto-stop,
	pause normale et pause suspecte.
- [ ] Détecter une vitesse nulle pendant une durée configurable.
- [x] Détecter une perte de signal ou l'absence de rapport PureTrack.
- [x] Conserver l'état `Unknown` tant qu'aucune donnée PureTrack récente n'est disponible.
- [ ] Utiliser la hauteur au-dessus du sol dans les décisions.
- [ ] Ignorer ou signaler les points PureTrack aberrants.
- [ ] Implémenter la règle de pause suspecte : absence de déplacement pendant
	une fenêtre donnée après une activité de vol significative.
- [ ] Ajouter des seuils configurables et documentés.

### 2. Scénarios de replay

- [ ] Capturer des scénarios représentatifs : vol, atterrissage, pause,
	perte de signal et alerte.
- [ ] Ajouter un format de version aux fichiers de replay.
- [ ] Vérifier que le replay et le monitoring réel utilisent exactement le
	même pipeline métier.
- [ ] Ajouter des tests de non-régression pour chaque transition importante.

### 3. Notifications et confirmations

- [ ] Définir les messages d'alerte destinés aux superviseurs.
- [ ] Ajouter téléphone et e-mail dans les alertes lorsque disponibles.
- [ ] Gérer explicitement une réponse négative.
- [ ] Gérer l'expiration et le renouvellement des confirmations.
- [ ] Gérer les erreurs Discord et les limitations de débit.
- [ ] Ajouter une stratégie de reprise après perte de connexion Discord.

### 4. Stockage et séparation des responsabilités

- [ ] Séparer les responsabilités PureTrack, détection, machine d'état,
	stockage, replay et notifications.
- [ ] Ajouter une abstraction de stockage pour faciliter les tests.
- [ ] Éviter les appels réseau et les effets de bord dans les constructeurs.
- [ ] Rendre les fenêtres temporelles et l'horloge injectables pour les tests.

### 5. Supervision

- [ ] Ajouter une interface web avec la liste des parapentistes.
- [ ] Afficher l'état courant, la dernière position et le dernier rapport.
- [ ] Ajouter un code couleur pour les situations normales et les alertes.
- [ ] Afficher l'historique récent d'un parapentiste.

### 6. Sécurité et déploiement

- [ ] Utiliser `DISCORD_BOT_TOKEN` pour tous les environnements d'exécution.
- [ ] Régénérer tout token Discord ayant été exposé.
- [ ] Ne jamais versionner les configurations contenant tokens, IDs ou données
	personnelles.
- [ ] Documenter les variables d'environnement et le démarrage Docker.
- [ ] Ajouter une vérification de configuration au démarrage.

## Critères de validation

- [ ] Tous les tests automatisés passent sans accès réseau.
- [ ] Un replay complet produit les mêmes transitions que le mode réel.
- [ ] Une alerte contient les informations nécessaires aux superviseurs.
- [ ] Une réponse depuis le canal ou un DM cible le bon parapentiste.
- [ ] Un même compte Discord peut confirmer plusieurs parapentistes sans
	ambiguïté.
- [ ] L'arrêt de l'application ferme proprement Discord, les tâches et les
	timers.