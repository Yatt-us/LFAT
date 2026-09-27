"""Vues core du tableau de bord."""

from .common import *
from ..access import school_role_required, assigned_programs, is_teacher_account
from ..finance import creances_avec_total
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import OuterRef, Subquery


@login_required
def initier_paiement(request):
    """Affiche l'attente d'abonnement et réserve la demande à la direction."""
    ecole = get_user_ecole(request)
    if not ecole:
        return HttpResponseForbidden('Aucune école associée à ce compte.')
    if ecole.peut_utiliser_systeme():
        messages.info(request, "L’accès de votre école est déjà actif.")
        return redirect('dashboard_accueil')

    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    can_submit_request = request.user.is_superuser or role in ('school_admin', 'director')
    demande = DemandeAbonnement.objects.filter(ecole=ecole, statut='pending').first()

    if request.method == 'POST':
        if not can_submit_request:
            return HttpResponseForbidden("Seule la direction peut soumettre une demande d'abonnement.")
        if demande:
            messages.info(request, "Une demande de paiement est déjà en attente de confirmation.")
        else:
            DemandeAbonnement.objects.create(ecole=ecole, montant=25000)
            messages.success(
                request,
                "Demande enregistrée. L’accès sera activé après confirmation du paiement par l’administration.",
            )
        return redirect('initier_paiement')

    return render(request, 'dashboard/paiements/initier_paiement.html', {
        'ecole': ecole,
        'montant': 25000,
        'demande': demande,
        'can_submit_request': can_submit_request,
    })


@school_role_required('school_admin', 'director', 'secretary', 'accountant')
def recherche_etudiants(request):
    query = request.GET.get('q', '').strip()
    ecole = get_user_ecole(request)
    resultats = []

    if not ecole:
        messages.warning(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if query:
        filtre_identite = (
            Q(nom__icontains=query)
            | Q(prenom__icontains=query)
            | Q(numero_matricule__icontains=query)
        )
        resultats = Etudiant.objects.filter(ecole=ecole)
        if annee_active:
            classe_courante = (
                Inscription.objects.filter(
                    ecole=ecole, etudiant_id=OuterRef('pk'),
                    annee_scolaire=annee_active,
                )
                .order_by()
                .values('classe__nom_classe')[:1]
            )
            resultats = resultats.annotate(
                classe_courante=Subquery(classe_courante)
            ).filter(filtre_identite | Q(classe_courante__icontains=query))
        else:
            resultats = resultats.filter(filtre_identite)
        resultats = resultats.select_related('ecole').order_by('nom', 'prenom')

    context = {
        'query': query,
        'resultats': resultats,
        'annee_active': annee_active,
    }
    return render(request, 'dashboard/etudiants/recherche_etudiants.html', context)

# ------------------------------------------------------------------
# TABLEAU DE BORD ACCUEIL (MULTI-ÉCOLE)
# ------------------------------------------------------------------


@school_role_required('school_admin', 'director', 'secretary', 'accountant', 'teacher')
def dashboard_accueil(request):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.warning(request, "Vous n'êtes associé à aucune école.")
        return HttpResponse('Aucune école n’est associée à ce compte.', status=403)

    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    is_superuser = request.user.is_superuser
    can_manage_students = is_superuser or role in ('school_admin', 'director', 'secretary')
    can_view_finances = is_superuser or role in ('school_admin', 'director', 'accountant')
    can_manage_years = is_superuser or role in ('school_admin', 'director')
    person_name = request.user.get_short_name().strip() or request.user.username
    role_labels = {
        'school_admin': 'Administration',
        'director': 'Direction',
        'secretary': 'Secrétariat',
        'accountant': 'Comptabilité',
        'teacher': 'Enseignement',
    }

    def action(label, description, icon, url_name):
        return {
            'label': label,
            'description': description,
            'icon': icon,
            'href': reverse(url_name),
        }

    overview_payload = {
        'variant': 'teacher' if is_teacher_account(request.user) else 'school',
        'schoolName': ecole.nom_etablissement,
        'year': annee_active.annee if annee_active else None,
        'personName': person_name,
        'roleLabel': 'Administration générale' if is_superuser else role_labels.get(role, 'Équipe scolaire'),
        'metrics': [],
        'actions': [],
    }

    if is_teacher_account(request.user):
        classes = []
        nombre_eleves = 0
        if annee_active:
            assignments = assigned_programs(request.user, ecole, annee_active)
            classes_queryset = Classe.objects.filter(
                ecole=ecole, pk__in=assignments.values('classe_id'),
                annee_scolaire=annee_active,
            ).distinct().order_by('nom_classe')
            classes = [
                {
                    'name': classe.nom_classe,
                    'href': reverse('suivi_presence_classe', args=[classe.pk]),
                }
                for classe in classes_queryset
            ]
            nombre_eleves = Etudiant.objects.filter(
                ecole=ecole,
                inscriptions__ecole=ecole,
                inscriptions__classe__in=classes_queryset,
                inscriptions__annee_scolaire=annee_active,
                inscriptions__statut='active',
            ).distinct().count()
            overview_payload['metrics'] = [
                {'label': 'Mes classes', 'value': len(classes), 'icon': 'classes', 'tone': 'indigo', 'hint': 'Classes affectées'},
                {'label': 'Élèves suivis', 'value': nombre_eleves, 'icon': 'students', 'tone': 'aqua', 'hint': 'Inscriptions actives'},
            ]
        overview_payload['classes'] = classes
        overview_payload['actions'] = [
            action('Emplois du temps', 'Consulter les cours', 'calendar', 'liste_emplois_du_temps'),
            action('Mes matières', 'Voir mes affectations', 'book', 'liste_programmes_matiere'),
            action('Notes', 'Consulter et saisir', 'notes', 'liste_notes_par_classe_matiere'),
            action('Présences', 'Suivre les classes', 'attendance', 'liste_presences'),
        ]
        return render(request, 'dashboard/dashboard_enseignant.html', {
            'overview_payload': overview_payload,
        })

    if can_manage_years and not annee_active:
        overview_payload['yearAction'] = action(
            'Configurer l’année scolaire', 'Créer ou activer une année', 'calendar', 'liste_annees_scolaires',
        )

    if can_manage_students:
        overview_payload['actions'].append(
            action('Élèves', 'Ouvrir les dossiers', 'students', 'liste_etudiants')
        )
        if annee_active:
            overview_payload['actions'].append(
                action('Nouvelle inscription', 'Ajouter un élève', 'plus', 'creer_etudiant')
            )
        overview_payload['actions'].extend([
            action('Classes', 'Gérer les groupes', 'classes', 'liste_classes'),
            action('Enseignants', 'Voir l’équipe', 'book', 'liste_enseignants'),
        ])
    if can_view_finances:
        overview_payload['actions'].append(
            action('Suivi des paiements', 'Consulter les frais', 'wallet', 'liste_paiements_par_classe_etudiant')
        )
    if is_superuser or role in ('school_admin', 'director'):
        overview_payload['actions'].append(
            action('Modèles de documents', 'Personnaliser les plans', 'document', 'modeles_documents')
        )
    if role == 'accountant' and not is_superuser:
        overview_payload['actions'].append(
            action('Rechercher un élève', 'Accéder au dossier financier', 'search', 'recherche_etudiants_globale')
        )

    if annee_active:
        inscriptions_actives = Inscription.objects.filter(
            ecole=ecole,
            annee_scolaire=annee_active,
            statut='active',
            etudiant__ecole=ecole,
        )
        nombre_eleves = inscriptions_actives.count()
        classes_actives = Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).count()
        enseignants_actifs = ecole.enseignants.count()
        absents_aujourd_hui = Presence.objects.filter(
            ecole=ecole,
            annee_scolaire=annee_active,
            date=timezone.localdate(),
            statut__in=('Absent', 'Excusé'),
            etudiant__ecole=ecole,
        ).values('etudiant_id').distinct().count()
        overview_payload['metrics'] = [
            {'label': 'Élèves inscrits', 'value': nombre_eleves, 'icon': 'students', 'tone': 'indigo', 'hint': 'Année active'},
            {'label': 'Classes actives', 'value': classes_actives, 'icon': 'classes', 'tone': 'aqua', 'hint': 'Année active'},
            {'label': 'Absents aujourd’hui', 'value': absents_aujourd_hui, 'icon': 'attendance', 'tone': 'amber', 'hint': 'Élèves distincts'},
            {'label': 'Enseignants', 'value': enseignants_actifs, 'icon': 'book', 'tone': 'slate', 'hint': 'Équipe de l’école'},
        ]

        # Les soldes financiers ne sont jamais calculés ni transmis aux rôles non autorisés.
        if can_view_finances:
            creances = list(creances_avec_total(ecole, annee_active))
            eleves_non_payes_compte = len({f.etudiant_id for f in creances if f.solde_restant > 0 or f.a_verifier})
            total_impaye = sum((f.solde_restant for f in creances), Decimal('0.00'))
            total_paye = Paiement.objects.filter(
                ecole=ecole, etudiant__ecole=ecole, annee_scolaire=annee_active,
                annule=False, montant__gt=0,
            ).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
            overview_payload['metrics'].extend([
                {'label': 'Encaissements', 'value': f'{total_paye:,.2f}'.replace(',', ' ').replace('.', ','), 'unit': 'FCFA', 'icon': 'wallet', 'tone': 'aqua', 'hint': 'Année active'},
                {'label': 'Restant à payer', 'value': f'{total_impaye:,.2f}'.replace(',', ' ').replace('.', ','), 'unit': 'FCFA', 'icon': 'wallet', 'tone': 'amber', 'hint': 'Solde des frais'},
                {'label': 'Élèves à régulariser', 'value': eleves_non_payes_compte, 'icon': 'attendance', 'tone': 'rose', 'hint': 'Frais dus ou à vérifier'},
            ])

        if can_manage_students:
            recent_inscriptions = inscriptions_actives.select_related(
                'etudiant', 'classe',
            ).order_by('-date_inscription', '-pk')[:4]
            overview_payload['recentStudents'] = [
                {
                    'name': f'{inscription.etudiant.prenom} {inscription.etudiant.nom}',
                    'className': inscription.classe.nom_classe if inscription.classe else 'Classe non assignée',
                    'date': inscription.date_inscription.strftime('%d/%m/%Y'),
                    'href': reverse('detail_etudiant', args=[inscription.etudiant_id]),
                }
                for inscription in recent_inscriptions
            ]
            overview_payload['studentsUrl'] = reverse('liste_etudiants')

    return render(request, 'dashboard/dashboard_accueil.html', {
        'overview_payload': overview_payload,
    })

# ------------------------------------------------------------------
# LISTE ÉTUDIANTS
# ------------------------------------------------------------------


@school_role_required('school_admin', 'director')
def config_ecole_view(request):
    """
    Gérer la configuration de l'école pour l'utilisateur connecté.
    Chaque utilisateur ne peut accéder qu'à sa propre école.
    """
    ecole = get_user_ecole(request)

    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # --- Récupérer la configuration existante de l'école ---
    settings = get_object_or_404(EcoleSettings, id=ecole.id)

    # --- Gestion du formulaire POST ---
    if request.method == 'POST':
        form = EcoleSettingsForm(request.POST, request.FILES, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Paramètres de l'école mis à jour avec succès."
            )
            return redirect('ecole_settings')
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = EcoleSettingsForm(instance=settings)

    # --- Rendu du template ---
    context = {
        'form': form,
        'settings': settings,
        'page_title': "Paramètres de l'École",
    }
    return render(request, 'dashboard/settings/config_ecole.html', context)

# ======================================================
# CARTE SCOLAIRE (HTML ou PDF)
# ======================================================
