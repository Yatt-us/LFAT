# Tableau de bord administrateur Angular

Cette application Angular s'affiche à l'accueil de l'administration Django (`/admin/`). Django prépare les indicateurs et demandes du super administrateur, puis les transmet dans la page avec `json_script`. Les formulaires de gestion et l'action de confirmation des paiements restent dans l'administration Django.

## Compilation

```bash
cd admin-frontend
npm ci
npm run build
```

Le build place les fichiers dans `dashboard/static/dashboard/admin-angular/`. Après déploiement, exécuter aussi `python manage.py collectstatic`. La commande `npm run dev` surveille les sources Angular dans `dist/` ; relancer `npm run build` pour copier la version finale vers Django.
