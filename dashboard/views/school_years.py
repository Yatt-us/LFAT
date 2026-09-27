"""Vues school years du tableau de bord."""

from .common import *
from ..access import school_role_required


@school_role_required('school_admin', 'director', 'secretary')
def liste_annees_scolaires(request):
    """
    Liste toutes les années scolaires pour l'école de l'utilisateur connecté
    et calcule l'année scolaire actuelle selon le calendrier.
    """
    # 🔹 Récupérer l'école de l'utilisateur
    ecole = get_user_ecole(request)

    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Filtrer par école
    annees_scolaires = AnneeScolaire.objects.filter(ecole=ecole).order_by('-annee')

    # 🔹 Calcul de l'année scolaire actuelle selon le calendrier
    today = timezone.localdate()
    if today.month >= 8:
        start_year = today.year
        end_year = today.year + 1
    else:
        start_year = today.year - 1
        end_year = today.year
    current_academic_year = f"{start_year}-{end_year}"

    context = {
        'annees_scolaires': annees_scolaires,
        'current_calendar_year': today.year,
        'current_academic_year_string': current_academic_year,
        'ecole': ecole,
    }
    return render(request, 'dashboard/annees_scolaires/liste_annees_scolaires.html', context)


@school_role_required('school_admin', 'director')
def creer_annee_scolaire(request):
    """Créer une nouvelle année scolaire pour l'école de l'utilisateur"""
    ecole = get_user_ecole(request)  # Récupération sécurisée de l'école
    if request.method == 'POST':
        form = AnneeScolaireForm(request.POST, ecole=ecole)
        if form.is_valid():
            annee = form.save(commit=False)
            annee.ecole = ecole  # Assigner l'école avant la sauvegarde
            annee.save()
            messages.success(request, "Année scolaire ajoutée avec succès.")
            return redirect('liste_annees_scolaires')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = AnneeScolaireForm(ecole=ecole)

    return render(request, 'dashboard/annees_scolaires/form_annee_scolaire.html', {
        'form': form,
        'action': 'Créer'
    })


@school_role_required('school_admin', 'director')
def modifier_annee_scolaire(request, pk):
    """Modifier une année scolaire existante de l'école de l'utilisateur"""
    ecole = get_user_ecole(request)
    annee = get_object_or_404(AnneeScolaire, pk=pk, ecole=ecole)  # ⚠️ Filtrage par école pour sécurité

    if request.method == 'POST':
        form = AnneeScolaireForm(request.POST, instance=annee, ecole=ecole)
        if form.is_valid():
            form.save()
            messages.success(request, "Année scolaire mise à jour avec succès.")
            return redirect('liste_annees_scolaires')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = AnneeScolaireForm(instance=annee, ecole=ecole)

    return render(request, 'dashboard/annees_scolaires/form_annee_scolaire.html', {
        'form': form,
        'action': 'Modifier'
    })


@school_role_required('school_admin', 'director')
def supprimer_annee_scolaire(request, pk):
    """Supprimer une année scolaire après confirmation"""
    ecole = get_user_ecole(request)
    annee = get_object_or_404(AnneeScolaire, pk=pk, ecole=ecole)

    if request.method == 'POST':
        has_data = any([
            Classe.objects.filter(annee_scolaire=annee).exists(),
            Etudiant.objects.filter(annee_scolaire_inscription=annee).exists(),
            Inscription.objects.filter(annee_scolaire=annee).exists(),
            Note.objects.filter(annee_scolaire=annee).exists(),
            Paiement.objects.filter(annee_scolaire=annee).exists(),
            CreanceScolaire.objects.filter(annee_scolaire=annee).exists(),
            Presence.objects.filter(annee_scolaire=annee).exists(),
            EmploiDuTemps.objects.filter(annee_scolaire=annee).exists(),
        ])
        if annee.active or has_data:
            messages.error(request, "Cette année est active ou contient des données. Désactivez-la ou archivez ses données avant toute suppression.")
            return redirect('liste_annees_scolaires')
        annee_nom = annee.annee
        annee.delete()
        messages.success(request, f"L'année scolaire {annee_nom} a été supprimée.")
        return redirect('liste_annees_scolaires')
    
    return render(request, 'dashboard/annees_scolaires/confirmer_suppression_annee_scolaire.html', {
        'annee': annee
    })


# ==========================
# CRUD Classes
# ==========================


@school_role_required('school_admin', 'director')
def activer_annee_scolaire(request, pk):
    ecole = get_user_ecole(request)
    annee = get_object_or_404(AnneeScolaire, pk=pk, ecole=ecole)
    if request.method != 'POST':
        return HttpResponse(status=405)
    annee.active = True
    annee.save(update_fields=['active'])
    messages.success(request, f"L’année {annee.annee} est maintenant active.")
    return redirect('liste_annees_scolaires')
