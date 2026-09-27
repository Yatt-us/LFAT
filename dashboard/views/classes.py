"""Vues classes du tableau de bord."""

from .common import *
from ..access import school_role_required, assigned_programs, is_teacher_account
from django.db.models.deletion import ProtectedError


@school_role_required('school_admin', 'director', 'secretary', 'teacher')
def liste_classes(request):
    """
    Liste toutes les classes de l'école de l'utilisateur,
    triées par année scolaire et nom, avec filtrage strict par école.
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    classes = Classe.objects.filter(ecole=ecole) \
                           .select_related('annee_scolaire', 'enseignant_principal') \
                           .order_by('annee_scolaire__annee', 'nom_classe')
    if is_teacher_account(request.user):
        classes = classes.filter(pk__in=assigned_programs(request.user, ecole).values('classe_id'))

    return render(request, 'dashboard/classes/liste_classes.html', {
        'classes': classes,
        'ecole': ecole
    })


@school_role_required('school_admin', 'director', 'secretary')
def creer_classe(request):
    """
    Créer une nouvelle classe pour l'école de l'utilisateur
    et assigner automatiquement l'année scolaire active.
    Filtre les champs du formulaire selon l'école.
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Récupérer la première année active pour cette école
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).order_by('-annee').first()
    if not annee_active:
        messages.warning(request, "Veuillez définir une année scolaire active avant de créer une classe.")
        return redirect('liste_annees_scolaires')

    if request.method == 'POST':
        form = ClasseForm(request.POST, ecole=ecole)
        if form.is_valid():
            classe = form.save(commit=False)
            classe.ecole = ecole
            classe.annee_scolaire = annee_active  # assigner automatiquement l'année active
            classe.save()
            messages.success(request, f"Classe '{classe.nom_classe}' ajoutée avec succès.")
            return redirect('liste_classes')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = ClasseForm(ecole=ecole)

    return render(request, 'dashboard/classes/form_classe.html', {
        'form': form,
        'action': 'Créer',
        'annee_active': annee_active,
    })


@school_role_required('school_admin', 'director', 'secretary')
def modifier_classe(request, pk):
    """
    Modifier une classe existante uniquement si elle appartient à l'école de l'utilisateur.
    Passe l'école au formulaire pour filtrer les champs liés (ex: matières, enseignants).
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)

    if request.method == 'POST':
        form = ClasseForm(request.POST, instance=classe, ecole=ecole)
        if form.is_valid():
            form.save()
            messages.success(request, "Classe mise à jour avec succès.")
            return redirect('liste_classes')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = ClasseForm(instance=classe, ecole=ecole)

    return render(request, 'dashboard/classes/form_classe.html', {
        'form': form,
        'action': 'Modifier'
    })


@school_role_required('school_admin', 'director')
def supprimer_classe(request, pk):
    """
    Supprimer une classe uniquement si elle appartient à l'école de l'utilisateur.
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    classe = get_object_or_404(Classe, pk=pk, ecole=ecole)

    if request.method == 'POST':
        if Presence.objects.filter(classe=classe).exists() or EmploiDuTemps.objects.filter(classe=classe).exists():
            messages.error(request, "Cette classe possède un historique de présences ou d'emploi du temps et ne peut pas être supprimée.")
            return redirect('liste_classes')
        nom_classe = classe.nom_classe
        try:
            classe.delete()
        except ProtectedError:
            messages.error(request, "Cette classe est utilisée par des inscriptions ou des évaluations et ne peut pas être supprimée.")
            return redirect('liste_classes')
        messages.success(request, f"La classe {nom_classe} a été supprimée.")
        return redirect('liste_classes')

    return render(request, 'dashboard/classes/confirmer_suppression_classe.html', {
        'classe': classe
    })


# ------------------ MATIERES ------------------
