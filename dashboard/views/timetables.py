"""Vues timetables du tableau de bord."""

from .common import *
from ..access import school_role_required, assigned_programs, is_teacher_account


@school_role_required('school_admin', 'director', 'secretary', 'teacher')
def liste_emplois_du_temps(request):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    peut_gerer_edt = request.user.is_superuser or role in ('school_admin', 'director', 'secretary')
    toutes_les_classes = Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).order_by('nom_classe')
    if is_teacher_account(request.user):
        toutes_les_classes = toutes_les_classes.filter(pk__in=assigned_programs(request.user, ecole, annee_active).values('classe_id'))

    classe_id = request.GET.get('classe_id')
    classe_selectionnee = get_object_or_404(toutes_les_classes, pk=classe_id) if classe_id else None
    classes_a_afficher = [classe_selectionnee] if classe_selectionnee else toutes_les_classes

    if not annee_active:
        messages.warning(request, "Veuillez définir une année scolaire active avant de consulter les emplois du temps.")
        return render(request, 'dashboard/emplois_du_temps/emplois_du_temps.html', {
            'annee_active': None,
            'toutes_les_classes': toutes_les_classes,
            'emplois_du_temps_par_classe': {},
            'heures_disponibles': [],
            'jours_semaine': EmploiDuTemps.JourSemaine.values,
            'peut_gerer_edt': peut_gerer_edt,
        })

    # Colonnes horaires
    plages_horaires = sorted([
        f"{p['heure_debut'].strftime('%H:%M')} - {p['heure_fin'].strftime('%H:%M')}"
        for p in EmploiDuTemps.objects.filter(
            annee_scolaire=annee_active,
            ecole=ecole
        ).values('heure_debut', 'heure_fin').distinct()
    ], key=lambda x: x.split(' - ')[0])

    jours_semaine = EmploiDuTemps.JourSemaine.values
    emplois_par_classe = {}

    for classe in classes_a_afficher:
        edt_items = EmploiDuTemps.objects.filter(
            classe=classe,
            annee_scolaire=annee_active,
            ecole=ecole
        ).select_related('matiere', 'enseignant')

        edt_dict = {jour: {plage: None for plage in plages_horaires} for jour in jours_semaine}
        for item in edt_items:
            plage_str = f"{item.heure_debut.strftime('%H:%M')} - {item.heure_fin.strftime('%H:%M')}"
            if item.jour in edt_dict and plage_str in edt_dict[item.jour]:
                edt_dict[item.jour][plage_str] = item
        emplois_par_classe[classe] = edt_dict

    return render(request, 'dashboard/emplois_du_temps/emplois_du_temps.html', {
        'annee_active': annee_active,
        'toutes_les_classes': toutes_les_classes,
        'classe_selectionnee': classe_selectionnee,
        'emplois_du_temps_par_classe': emplois_par_classe,
        'heures_disponibles': plages_horaires,
        'jours_semaine': jours_semaine,
        'peut_gerer_edt': peut_gerer_edt,
    })


# ==========================
# 🔹 CRÉATION GÉNÉRALE D'EMPLOI DU TEMPS
# ==========================


@school_role_required('school_admin', 'director', 'secretary')
def creer_emploi_du_temps(request, classe_pk=None):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.error(request, 'Définissez une année scolaire active avant de créer un cours.')
        return redirect('liste_annees_scolaires')
    classe = get_object_or_404(Classe, pk=classe_pk, ecole=ecole, annee_scolaire=annee_active) if classe_pk else None

    if request.method == 'POST':
        form = EmploiDuTempsForm(request.POST, ecole=ecole, annee_scolaire=annee_active)
        if form.is_valid():
            edt = form.save(commit=False)
            edt.ecole = ecole
            edt.annee_scolaire = annee_active
            edt.save()
            messages.success(request, "Le bloc de cours a été enregistré avec succès !")
            return redirect('liste_emplois_du_temps')
        messages.error(request, "Erreur lors de l'enregistrement. Vérifiez les champs.")
    else:
        initial = {'classe': classe} if classe else {}
        form = EmploiDuTempsForm(initial=initial, ecole=ecole, annee_scolaire=annee_active)

    context = {
        'form': form,
        'classe': classe,
        'action': "Créer" if not request.GET.get('edit') else "Modifier",
    }
    return render(request, 'dashboard/emplois_du_temps/emploi_du_temps_form.html', context)


# ==========================
# 🔹 CRÉATION POUR UNE CLASSE SPÉCIFIQUE
# ==========================


@school_role_required('school_admin', 'director', 'secretary')
def creer_emploi_du_temps_pour_classe(request, classe_id):
    # 🔹 Récupération de l'école de l'utilisateur
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Vérification que la classe appartient à cette école
    classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole)

    # 🔹 Année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.error(request, "Aucune année scolaire active n’a été trouvée.")
        return redirect('liste_emplois_du_temps')
    if classe.annee_scolaire_id != annee_active.pk:
        return HttpResponse('Cette classe appartient à une autre année scolaire.', status=400)

    if request.method == "POST":
        # 🔹 On passe l'école à notre formulaire pour filtrer les classes, matières et enseignants
        form = EmploiDuTempsForm(request.POST, ecole=ecole, annee_scolaire=annee_active, fixed_classe=classe)
        if form.is_valid():
            edt = form.save(commit=False)
            edt.ecole = ecole
            edt.classe = classe
            edt.annee_scolaire = annee_active
            edt.save()
            messages.success(request, f"Emploi du temps ajouté pour {classe.nom_classe}.")
            return redirect('liste_emplois_du_temps')
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = EmploiDuTempsForm(ecole=ecole, annee_scolaire=annee_active, fixed_classe=classe)

    return render(request, 'dashboard/emplois_du_temps/form_emploi_du_temps.html', {
        'form': form,
        'action': f"Créer pour {classe.nom_classe}",
        'classe': classe,
    })


# ==========================
# 🔹 MODIFICATION D'UN EMPLOI DU TEMPS
# ==========================


@school_role_required('school_admin', 'director', 'secretary')
def modifier_emploi_du_temps(request, pk):
    # 🔹 Récupération de l'école de l'utilisateur connecté
    ecole_utilisateur = get_user_ecole(request)
    if not ecole_utilisateur:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Récupérer le bloc uniquement s'il appartient à cette école
    bloc_edt = get_object_or_404(EmploiDuTemps, pk=pk, ecole=ecole_utilisateur)

    if request.method == 'POST':
        # 🔹 Passer l'école au formulaire pour filtrer les choix
        form = EmploiDuTempsForm(request.POST, instance=bloc_edt, ecole=ecole_utilisateur, annee_scolaire=bloc_edt.annee_scolaire)
        if form.is_valid():
            form.save()
            messages.success(request, "Bloc d'emploi du temps mis à jour avec succès !")
            return redirect('liste_emplois_du_temps')
        messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = EmploiDuTempsForm(instance=bloc_edt, ecole=ecole_utilisateur, annee_scolaire=bloc_edt.annee_scolaire)

    return render(request, 'dashboard/emplois_du_temps/form_emploi_du_temps.html', {
        'form': form,
        'action': 'Modifier'
    })

# ==========================
# 🔹 REDIRECTION MODIFICATION CLASSE
# ==========================


@school_role_required('school_admin', 'director', 'secretary')
def modifier_emploi_du_temps_classe(request, classe_id):
    messages.error(request, "La modification doit se faire bloc par bloc. Utilisez l'icône d'édition dans le tableau.")
    return redirect('liste_emplois_du_temps')
# ==========================
# Saisie de notes
# ==========================
