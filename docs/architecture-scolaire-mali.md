# Architecture scolaire pour le Mali

## Références vérifiées

- La [loi malienne n° 99-046 du 28 décembre 1999](https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/97009/MLI-97009.pdf) distingue l'enseignement fondamental et l'enseignement secondaire. Le fondamental dure neuf ans et se conclut par le DEF (articles 29 et 33 à 38).
- Le [programme décennal de développement de l'éducation 2019-2028 du ministère](https://natlex.ilo.org/dyn/natlex2/natlex2/files/download/112244/MLI-112244.pdf) décrit le fondamental en deux cycles de six et trois ans, puis le secondaire général en trois ans (section 2.1.1).
- Le [décret malien n° 2011-234/P-RM](https://sgg-mali.ml/JO/2011/mali-jo-2011-25.pdf) nomme les années 10e, 11e et 12e, avec une 10e commune et des séries à partir de la 11e (articles 3 à 5). La liste exacte des séries et ses éventuelles évolutions doivent être vérifiées auprès des établissements pilotes avant de devenir une contrainte bloquante.

Ces textes définissent l'organisation des cycles. Ils ne suffisent pas, à eux seuls, à imposer une formule universelle de moyenne, un découpage en trimestres ou une maquette unique de bulletin. Ces choix doivent être renseignés par l'établissement pour l'année et le cycle concernés. Le PDF et les données calculées sont figés lors de la publication d'un bulletin.

## État de l'application

| Domaine | Implémenté dans cette branche | Limite à traiter |
| --- | --- | --- |
| Identité et scolarité | `Etudiant` conserve l'identité ; `Inscription` porte l'école, l'année, la classe et le statut annuels. Les écrans courants lisent l'inscription. `AffectationClasse` conserve les mutations datées, avec une seule affectation ouverte par inscription. | `Etudiant.classe` subsiste comme champ de compatibilité. La reprise initiale ne connaît que la classe courante au jour de migration ; elle ne reconstruit pas les transferts anciens. |
| Cycles et programme | Les niveaux du fondamental et du lycée sont proposés ; `ProgrammeMatiere` relie classe, matière, enseignant et coefficient positif. | Le programme et les coefficients ne sont pas versionnés dans le temps. Les séries et règles locales demandent validation avec les écoles pilotes. |
| Évaluations | `Evaluation` et `ResultatEvaluation` permettent plusieurs épreuves pondérées par matière, période et inscription. Le calcul du bulletin contrôle les résultats manquants et la coexistence avec les anciennes `Note`. | Les périodes sont encore des libellés de trimestre, sans dates configurées par école et année. Les anciennes notes restent à rapprocher avant certains bulletins. |
| Règle annuelle | `RegleBulletinAnnuel` fixe, par école, année et cycle (`fondamental_1`, `fondamental_2`, `lycee`), trois poids explicites. La direction ou l'administration doit valider la règle ; modifier un poids retire cette validation. Un poids nul exclut le trimestre, les autres trimestres doivent être complets. | Aucune règle ni aucun poids n'est créé automatiquement. Chaque école doit saisir et valider sa propre politique ; seuils et mentions restent à définir avec elle. |
| Bulletin et documents | Un GET présente l'aperçu du bulletin complet ; la publication par POST archive le PDF, les données sources et un code de vérification. Une nouvelle publication modifiée annule le bulletin courant de la même période, conserve l'ancien PDF et révoque son code. La direction peut aussi annuler un document émis avec un motif. Les plans des documents sont personnalisables par école. La migration 0032 retire les valeurs par défaut de ministère, académie, nom et adresse d'un établissement précis pour les nouveaux certificats ; l'émission reprend l'identité de l'école et exige un lieu de délivrance renseigné. | Le rang, le conseil de classe, les décisions de passage et les règles officielles propres à chaque établissement ne sont pas encore modélisés. Les anciens enregistrements gardent leurs valeurs et demandent une revue manuelle, y compris le lieu de délivrance hors Bamako. |
| Assiduité | Le registre journalier `Presence` reste disponible. `Seance`, `Pointage` et `Justification` permettent l'appel par cours, le retard en minutes et une décision tracée sur une absence ou un retard. Une absence justifiée reste une absence dans les indicateurs. | L'appel par séance et le registre journalier coexistent ; leur rapprochement métier reste à préciser. Les pièces justificatives privées et les notifications aux familles ne sont pas encore un parcours complet. |
| Emploi du temps | Les formulaires détectent les chevauchements de classe et d'enseignant ; les séances vérifient aussi les horaires. | Les salles et une garantie transactionnelle ou en base contre tous les chevauchements restent à construire. |
| Finances | Créances, paiements et reçus sont liés à l'école et à l'année. | Échéanciers, rapprochement comptable et information des familles restent à approfondir. |

## Parcours actuellement utilisables

1. L'école crée son année, ses classes de fondamental ou de lycée, puis son programme de matières avec coefficients et enseignants.
2. Elle inscrit les élèves pour l'année. La classe et le statut courants sont ceux de l'inscription annuelle ; une mutation ouvre une nouvelle affectation datée sans réécrire la précédente.
3. Elle crée les évaluations et saisit les résultats par élève inscrit. Pour une matière et un trimestre donnés, le calcul utilise les évaluations détaillées ou une ancienne note, et bloque une double source ou un résultat manquant.
4. Pour un bulletin annuel, la direction saisit puis valide les poids de chaque cycle utilisé. Le calcul exige les bulletins complets des trimestres dont le poids est positif et refuse de déduire une formule implicite.
5. La direction examine l'aperçu, publie le bulletin archivé, puis peut révoquer explicitement un document avec motif. Le fichier déjà émis n'est pas recalculé silencieusement.
6. L'établissement peut faire l'appel journalier ou créer des séances avec pointages et justifications ; ces deux registres doivent encore être articulés dans sa procédure interne.

## Déploiement piloté des données existantes

1. **Sauvegarder avant toute migration.** Conserver une copie vérifiée de la base, des fichiers privés et des PDF émis, puis restaurer cette copie dans un environnement de préproduction. Prévoir le retour arrière avant de modifier la production.
2. **Mesurer sans corriger automatiquement.** Sur la copie, lancer `env/bin/python manage.py audit_integrite_scolaire`. Cette commande n'affiche que des comptes agrégés : incohérences école/année/classe/inscription, notes et matières hors programme, dates invalides, anciens en-têtes de certificats, chevauchements d'emploi du temps. Examiner ensuite les dossiers concernés dans un cadre sécurisé et corriger manuellement les anomalies à la source ; relancer l'audit jusqu'à obtenir des chiffres expliqués.
3. **Appliquer les migrations dans l'ordre.** Vérifier d'abord `env/bin/python manage.py showmigrations dashboard`. Sur la copie restaurée, appliquer la chaîne **0028 → 0032** : 0028 adapte niveaux et coefficients, 0029 ajoute évaluations et résultats, 0030 trace l'annulation des documents, 0031 ajoute les règles annuelles et 0032 retire les faux en-têtes par défaut des certificats. `env/bin/python manage.py migrate dashboard 0032` applique les dépendances manquantes ; appliquer ensuite les migrations des autres applications prêtes, dont `parcours_scolaire`, avec `env/bin/python manage.py migrate`. Lancer alors `env/bin/python manage.py auditer_affectations` pour contrôler la reprise.
4. **Configurer une école pilote.** Choisir un établissement volontaire couvrant les cycles réellement utilisés ; rapprocher inscriptions, classes, programmes et anciennes notes. Saisir ses poids annuels, puis les faire valider par une personne autorisée. Utiliser un exemple anonymisé de bulletin pour chaque cycle présent et faire approuver les textes, mentions et seuils locaux par l'école.
5. **Observer le parcours réel.** Vérifier les évaluations et résultats manquants, le calcul annuel, l'aperçu, la publication, le téléchargement du PDF et l'état du code de vérification après remplacement ou annulation. Vérifier aussi l'appel par séance, les retards, les justifications, les reçus et les accès entre écoles. Corriger les écarts relevés avant d'ouvrir à d'autres établissements.
6. **Étendre progressivement.** Garder les anciennes notes et pièces consultables pendant le rapprochement. Généraliser école par école avec le même audit, une sauvegarde et une validation métier ; retirer les champs doublons seulement après consolidation de l'historique.

## Décisions et limites restantes

- **Périodes datées** : définir les dates et le nombre de périodes par école, année et cycle ; relier les évaluations à ces fenêtres au lieu de se fier seulement au libellé « Trimestre ».
- **Historique de classe** : la migration reprend seulement la classe courante des inscriptions actives cohérentes encore dans leur année scolaire. Les transferts antérieurs inconnus ne peuvent pas être reconstruits automatiquement ; lancer `env/bin/python manage.py auditer_affectations` après migration, puis rapprocher les cas signalés manuellement.
- **Programme versionné** : conserver le coefficient, l'enseignant et la liste des matières applicables à la date d'une évaluation ou d'un bulletin publié.
- **Décisions pédagogiques** : définir rangs, mentions, seuils, conseils de classe, passages, redoublements, dispenses et absences aux compositions avec les établissements pilotes.
- **Tuteurs et communication** : modéliser les responsables légaux, leurs coordonnées, consentements et accès ; décider des notifications d'assiduité et de paiement.
- **Terrain et faible connectivité** : concevoir un mode hors ligne avec synchronisation et traitement explicite des conflits avant de le promettre aux écoles.
- **Documents administratifs** : revoir les anciens certificats avec en-tête codé en dur, vérifier leur lieu de délivrance et faire approuver les modèles par chaque école.

## État de la base locale au 27 septembre 2026

La base SQLite locale a été sauvegardée dans `private_backups/` (dossier ignoré par Git), puis les migrations ont été essayées sur une copie. La copie et la base locale migrée passent `PRAGMA integrity_check`, sans erreur de clé étrangère. Les **65 tests Django** des trois applications scolaires et `manage.py check` passent. Cela vérifie les scénarios codés et la structure de la base ; cela ne remplace pas une recette métier avec un établissement.

L'audit sur la base locale migrée signale trois inscriptions actives sans affectation datée ouverte, toutes datées après la fin de leur année scolaire. Il signale aussi une année aux dates invalides, une ancienne note hors programme, une ancienne note datée hors de l'année, un cours hors programme, un frais encaissé au-delà du montant dû et deux anciens certificats avec en-tête codé en dur. Ces comptes peuvent se recouper. Aucune date scolaire, note, somme ou pièce émise n'a été inventée ou corrigée automatiquement : les responsables de l'école doivent rapprocher les dossiers sources avant correction.

## Benchmark des offres publiquement décrites au Mali

Les pages des éditeurs décrivent leurs produits, sans constituer une preuve indépendante du fonctionnement réel. Elles servent ici à identifier des attentes, pas à copier leur code ou leur présentation.

| Attente observée | Exemples publics | État du projet / priorité |
| --- | --- | --- |
| Appel rapide sur téléphone, fonctionnement avec réseau faible, information des familles | [Scolynx](https://scolynx.com/), [Easy School](https://www.easysoftwares.net/fr/solutions/easy-school) | Appel par séance et retard en minutes disponibles ; mode hors connexion et notifications restent à construire. |
| Suivi des notes manquantes et bulletin seulement complet | [Scolynx](https://scolynx.com/), [Scolaria](https://malischool.com/) | Évaluations multiples et blocage des bulletins incomplets disponibles ; règles annuelles à configurer par école. |
| Emploi du temps sans conflit, gestion des salles | [Scolaria](https://malischool.com/), [MITICSchool](https://www.miticschool.com/) | Conflits classe/enseignant contrôlés dans les formulaires ; salles et garantie en base à ajouter. |
| Dossiers et historique annuel, tuteurs, conseil de classe | [MITICSchool](https://www.miticschool.com/), [Scolynx](https://scolynx.com/) | Inscription annuelle et affectations datées en place ; transferts antérieurs à la reprise inconnus, tuteurs et conseil à ajouter. |
| Encaissements FCFA, échéanciers, reçus, communication parents | [MITICSchool](https://www.miticschool.com/), [Easy School](https://www.easysoftwares.net/fr/solutions/easy-school) | Créances et reçus en place ; échéancier, rapprochement et notifications à renforcer. |

### Ordre de livraison recommandé après le pilote

1. Vérifier la reprise des affectations de classe, ajouter les périodes datées, puis verrouiller les sources de calcul historiques.
2. Ajouter la version du programme, les décisions de conseil et les tuteurs.
3. Renforcer les échanges avec les familles, les échéanciers et les rapports par cycle.
4. Concevoir l'accès hors ligne après observation de la connectivité et des usages de l'école pilote.
