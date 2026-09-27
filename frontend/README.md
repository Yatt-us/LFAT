# Interface React du tableau de bord

Django conserve les routes, les sessions, les autorisations et les formulaires. React est monté dans la navigation, l’accueil et l’annuaire des élèves. Les données affichées sont préparées par les vues Django de l’école connectée puis placées dans la page avec `json_script`.

## Construire les ressources

```bash
cd frontend
npm ci
npm run build
```

Le build écrit `app.js` et `app.css` dans `dashboard/static/dashboard/dist/`. Ces fichiers sont servis par les fichiers statiques Django. Pour reconstruire après chaque modification pendant le développement, utiliser `npm run dev` dans un autre terminal.

Après un déploiement, reconstruire le frontend puis exécuter `python manage.py collectstatic` dans l’environnement Django. Les fichiers `node_modules` ne sont pas versionnés.
