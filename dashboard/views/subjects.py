"""Vues subjects du tableau de bord."""

from .common import *
from ..access import school_role_required, assigned_programs, is_teacher_account
from django.db.models.deletion import ProtectedError


@school_role_required('school_admin', 'director', 'secretary', 'teacher')
def liste_matieres(request):
    """Liste des matières filtrée par école"""
    ecole = get_user_ecole(request)

    matieres = Matiere.objects.filter(ecole=ecole).order_by('nom')
    if is_teacher_account(request.user):
        matieres = matieres.filter(pk__in=assigned_programs(request.user, ecole).values('matiere_id'))
    return render(request, 'dashboard/matieres/liste_matieres.html', {'matieres': matieres, 'ecole': ecole})


@school_role_required('school_admin', 'director', 'secretary')
def creer_matiere(request):
    """Créer une matière liée à l'école de l'utilisateur"""
    ecole = get_user_ecole(request)

    if request.method == 'POST':
        form = MatiereForm(request.POST)
        if form.is_valid():
            matiere = form.save(commit=False)
            matiere.ecole = ecole
            matiere.save()
            messages.success(request, "Matière ajoutée avec succès.")
            return redirect('liste_matieres')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = MatiereForm()
    
    return render(request, 'dashboard/matieres/form_matiere.html', {'form': form, 'action': 'Créer'})


@school_role_required('school_admin', 'director', 'secretary')
def modifier_matiere(request, pk):
    """Modifier une matière uniquement si elle appartient à l'école de l'utilisateur"""
    ecole = get_user_ecole(request)

    matiere = get_object_or_404(Matiere, pk=pk, ecole=ecole)

    if request.method == 'POST':
        form = MatiereForm(request.POST, instance=matiere)
        if form.is_valid():
            form.save()
            messages.success(request, "Matière mise à jour avec succès.")
            return redirect('liste_matieres')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = MatiereForm(instance=matiere)
    
    return render(request, 'dashboard/matieres/form_matiere.html', {'form': form, 'action': 'Modifier'})


@school_role_required('school_admin', 'director')
def supprimer_matiere(request, pk):
    """Supprimer une matière uniquement si elle appartient à l'école de l'utilisateur"""
    ecole = get_user_ecole(request)

    matiere = get_object_or_404(Matiere, pk=pk, ecole=ecole)

    if request.method == 'POST':
        if Note.objects.filter(matiere=matiere).exists():
            messages.error(request, "Cette matière possède des notes historiques et ne peut pas être supprimée.")
            return redirect('liste_matieres')
        if Presence.objects.filter(matiere=matiere).exists() or EmploiDuTemps.objects.filter(matiere=matiere).exists():
            messages.error(request, "Cette matière possède un historique de présences ou d'emploi du temps et ne peut pas être supprimée.")
            return redirect('liste_matieres')
        nom_matiere = matiere.nom
        try:
            matiere.delete()
        except ProtectedError:
            messages.error(request, "Cette matière est utilisée par des évaluations ou des dossiers conservés.")
            return redirect('liste_matieres')
        messages.success(request, f"La matière {nom_matiere} a été supprimée.")
        return redirect('liste_matieres')
    
    return render(request, 'dashboard/matieres/confirmer_suppression_matiere.html', {'matiere': matiere})


# ==========================
# CRUD Enseignants
# ==========================


@school_role_required('school_admin', 'director', 'teacher')
def liste_programmes_matiere(request):
    # Récupérer l'école de l'utilisateur
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Récupérer l'année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre école.")
        return redirect('liste_annees_scolaires')

    # Filtrer les programmes de matière par école et année scolaire active
    programmes = ProgrammeMatiere.objects.filter(
        ecole=ecole, classe__ecole=ecole,
        classe__annee_scolaire=annee_active
    )
    if is_teacher_account(request.user):
        programmes = programmes.filter(enseignant__user=request.user)
    programmes = programmes.select_related('classe', 'matiere', 'enseignant').order_by('classe__nom_classe', 'matiere__nom')

    return render(request, 'dashboard/programmes_matiere/liste_programmes_matiere.html', {
        'programmes': programmes,
        'annee_active': annee_active,
    })


@school_role_required('school_admin', 'director')
def creer_programme_matiere(request):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    if request.method == 'POST':
        form = ProgrammeMatiereForm(request.POST, ecole=ecole)
        if form.is_valid():
            programme = form.save(commit=False)
            programme.ecole = ecole  # affecte l’école automatiquement
            programme.save()
            messages.success(request, "Programme matière ajouté avec succès.")
            return redirect('liste_programmes_matiere')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = ProgrammeMatiereForm(ecole=ecole)

    return render(request, 'dashboard/programmes_matiere/form_programme_matiere.html', {
        'form': form,
        'action': 'Créer'
    })


@school_role_required('school_admin', 'director')
def modifier_programme_matiere(request, pk):
    # Récupérer l'école de l'utilisateur connecté
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Récupérer le programme matière pour l'école courante
    programme = get_object_or_404(
        ProgrammeMatiere.objects.select_related('classe', 'matiere', 'enseignant'),
        pk=pk,
        classe__ecole=ecole  # 🔥 Filtrage strict par école via la classe
    )

    # Création du formulaire
    if request.method == 'POST':
        form = ProgrammeMatiereForm(request.POST, instance=programme, ecole=ecole)
        if form.is_valid():
            form.save()
            messages.success(request, "Programme matière mis à jour avec succès.")
            return redirect('liste_programmes_matiere')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = ProgrammeMatiereForm(instance=programme, ecole=ecole)

    return render(request, 'dashboard/programmes_matiere/form_programme_matiere.html', {
        'form': form,
        'action': 'Modifier',
        'programme': programme
    })


@school_role_required('school_admin', 'director')
def supprimer_programme_matiere(request, pk):
    # récupérer l'école de l'utilisateur
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # essayer de récupérer le programme pour cette école
    try:
        # on suppose que ProgrammeMatiere est lié à une classe (classe) et que la classe a un champ ecole
        programme = ProgrammeMatiere.objects.get(pk=pk, classe__ecole=ecole)
    except ProgrammeMatiere.DoesNotExist:
        messages.error(request, "Programme introuvable ou n'appartient pas à votre école.")
        return redirect('liste_programmes_matiere')

    # confirmation POST -> suppression
    if request.method == 'POST':
        notes_classe = Note.objects.filter(
            ecole=ecole, matiere=programme.matiere,
            annee_scolaire=programme.classe.annee_scolaire,
            etudiant__inscriptions__classe=programme.classe,
            etudiant__inscriptions__annee_scolaire=programme.classe.annee_scolaire,
        )
        if notes_classe.exists():
            messages.error(request, "Ce programme possède des notes historiques et ne peut pas être supprimé.")
            return redirect('liste_programmes_matiere')
        if (Presence.objects.filter(classe=programme.classe, matiere=programme.matiere).exists()
                or EmploiDuTemps.objects.filter(classe=programme.classe, matiere=programme.matiere).exists()):
            messages.error(request, "Ce programme possède un historique de cours ou de présences et ne peut pas être supprimé.")
            return redirect('liste_programmes_matiere')
        nom_complet = f"{programme.matiere.nom} pour {programme.classe.nom_classe}"
        try:
            programme.delete()
        except ProtectedError:
            messages.error(request, "Ce programme est utilisé par des évaluations et ne peut pas être supprimé.")
            return redirect('liste_programmes_matiere')
        messages.success(request, f"Le programme matière '{nom_complet}' a été supprimé.")
        return redirect('liste_programmes_matiere')

    # GET -> afficher confirmation
    return render(request, 'dashboard/programmes_matiere/confirmer_suppression_programme_matiere.html', {
        'programme': programme
    })


# --- CRUD pour les Notes ---
# Les fonctions ajouter/modifier/supprimer note sont généralement liées à la page détail élève.
# On a déjà ajouter_note ci-dessus. Voici un exemple pour modifier_note.
