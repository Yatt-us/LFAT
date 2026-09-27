"""Vues staff du tableau de bord."""

from .common import *
from ..access import school_role_required


@school_role_required('school_admin', 'director', 'secretary')
def liste_enseignants(request):
    """Liste des enseignants filtrée par l'école de l'utilisateur"""
    ecole = (
        getattr(getattr(request.user, 'enseignant', None), 'ecole', None)
        or getattr(getattr(request.user, 'profile', None), 'ecole', None)
        or (EcoleSettings.objects.first() if request.user.is_superuser else None)
    )

    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    enseignants = Enseignant.objects.filter(ecole=ecole).order_by('nom', 'prenom')
    return render(request, 'dashboard/enseignants/liste_enseignants.html', {'enseignants': enseignants, 'ecole': ecole})


@school_role_required('school_admin', 'director', 'secretary')
def creer_enseignant(request):
    ecole = (
        getattr(getattr(request.user, 'enseignant', None), 'ecole', None)
        or getattr(getattr(request.user, 'profile', None), 'ecole', None)
        or (EcoleSettings.objects.first() if request.user.is_superuser else None)
    )

    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    if request.method == 'POST':
        form = EnseignantForm(request.POST)
        if form.is_valid():
            enseignant = form.save(commit=False)
            enseignant.ecole = ecole  # Associer automatiquement l'école
            enseignant.save()
            messages.success(request, f"L'enseignant {enseignant.prenom} {enseignant.nom} a été ajouté avec succès.")
            return redirect('liste_enseignants')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = EnseignantForm()
    
    return render(request, 'dashboard/enseignants/form_enseignant.html', {'form': form, 'action': 'Créer'})


@school_role_required('school_admin', 'director', 'secretary')
def modifier_enseignant(request, pk):
    enseignant = get_object_or_404(Enseignant, pk=pk)

    # Vérifier que l'enseignant appartient à l'école de l'utilisateur
    ecole = (
        getattr(getattr(request.user, 'enseignant', None), 'ecole', None)
        or getattr(getattr(request.user, 'profile', None), 'ecole', None)
        or (EcoleSettings.objects.first() if request.user.is_superuser else None)
    )
    if not request.user.is_superuser and enseignant.ecole != ecole:
        messages.error(request, "Vous n'êtes pas autorisé à modifier cet enseignant.")
        return redirect('dashboard_accueil')

    if request.method == 'POST':
        form = EnseignantForm(request.POST, instance=enseignant)
        if form.is_valid():
            form.save()
            messages.success(request, f"L'enseignant {enseignant.prenom} {enseignant.nom} a été mis à jour.")
            return redirect('liste_enseignants')
        messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = EnseignantForm(instance=enseignant)
    
    return render(request, 'dashboard/enseignants/form_enseignant.html', {'form': form, 'action': 'Modifier'})


@school_role_required('school_admin', 'director')
def supprimer_enseignant(request, pk):
    enseignant = get_object_or_404(Enseignant, pk=pk)

    ecole = (
        getattr(getattr(request.user, 'enseignant', None), 'ecole', None)
        or getattr(getattr(request.user, 'profile', None), 'ecole', None)
        or (EcoleSettings.objects.first() if request.user.is_superuser else None)
    )
    if not request.user.is_superuser and enseignant.ecole != ecole:
        messages.error(request, "Vous n'êtes pas autorisé à supprimer cet enseignant.")
        return redirect('dashboard_accueil')

    if request.method == 'POST':
        nom_complet = f"{enseignant.prenom} {enseignant.nom}"
        enseignant.delete()
        messages.success(request, f"L'enseignant {nom_complet} a été supprimé.")
        return redirect('liste_enseignants')
    
    return render(request, 'dashboard/enseignants/confirmer_suppression_enseignant.html', {'enseignant': enseignant})


# ==========================
# CRUD Programmes Matières
# ==========================
