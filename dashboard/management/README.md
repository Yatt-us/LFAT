# Audit d'intégrité scolaire

Depuis la racine du projet :

```bash
env/bin/python manage.py audit_integrite_scolaire
```

La commande affiche uniquement des nombres d'incohérences concernant les années, classes, inscriptions, notes, présences et emplois du temps. Elle ne montre aucun nom d'élève et n'apporte aucune correction. Les catégories peuvent se recouper ; examiner les données concernées dans un environnement sécurisé avant toute migration.
