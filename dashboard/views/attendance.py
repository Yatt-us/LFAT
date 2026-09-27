"""Vues attendance du tableau de bord."""

from .common import *
from ..access import school_role_required, assigned_programs, teacher_can_teach, is_teacher_account


@school_role_required('school_admin', 'director', 'teacher')
def marquer_presence_classe(request, classe_id):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole)
    date_aujourdhui = timezone.localdate()
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.warning(request, "Veuillez définir une année scolaire active avant de marquer les présences.")
        return redirect('liste_annees_scolaires')
    if classe.annee_scolaire_id != annee_active.pk:
        return HttpResponse('Cette classe appartient à une autre année scolaire.', status=400)
    if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, classe.pk, year=annee_active):
        return HttpResponse('Vous n’êtes pas affecté à cette classe.', status=403)

    etudiants = list(Etudiant.objects.filter(
        ecole=ecole, inscriptions__classe=classe,
        inscriptions__annee_scolaire=annee_active, inscriptions__statut='active',
    ).order_by('nom', 'prenom', 'pk'))
    existing_presences = {
        presence.etudiant_id: presence for presence in Presence.objects.filter(
            classe=classe, date=date_aujourdhui, annee_scolaire=annee_active, ecole=ecole,
        )
    }
    initial_data = []
    for etudiant in etudiants:
        presence = existing_presences.get(etudiant.pk)
        initial_data.append({
            'etudiant': etudiant,
            'etudiant_obj': etudiant,
            'statut_saisie': presence.statut if presence else '',
            'matiere': presence.matiere_id if presence else None,
            'heure_debut_cours': presence.heure_debut_cours if presence else None,
            'heure_fin_cours': presence.heure_fin_cours if presence else None,
            'motif_absence_retard': presence.motif_absence_retard if presence else '',
            'justificatif_fourni': presence.justificatif_fourni if presence else False,
        })

    PresenceFormSet = formset_factory(PresenceForm, extra=0, max_num=len(etudiants), validate_max=True)
    form_kwargs = {
        'ecole': ecole, 'classe': classe, 'annee_scolaire': annee_active, 'user': request.user,
    }
    if request.method == 'POST':
        formset = PresenceFormSet(request.POST, initial=initial_data, form_kwargs=form_kwargs)
        if formset.is_valid():
            posted_ids = [form.cleaned_data['etudiant'].pk for form in formset]
            expected_ids = [etudiant.pk for etudiant in etudiants]
            if posted_ids != expected_ids:
                messages.error(request, "La liste des élèves a changé. Rechargez la page avant d'enregistrer.")
            else:
                from django.db import IntegrityError
                try:
                    enregistres = 0
                    renseignes = 0
                    with transaction.atomic():
                        for form in formset:
                            statut = form.cleaned_data['statut_saisie']
                            if not statut:
                                continue
                            renseignes += 1
                            presence, created = Presence.objects.get_or_create(
                                etudiant=form.cleaned_data['etudiant'],
                                classe=classe, date=date_aujourdhui,
                                annee_scolaire=annee_active, ecole=ecole,
                                defaults={'statut': statut},
                            )
                            valeurs = {'statut': statut}
                            if statut == 'Présent':
                                valeurs.update(
                                    matiere=None, heure_debut_cours=None, heure_fin_cours=None,
                                    motif_absence_retard='', justificatif_fourni=False,
                                )
                            else:
                                valeurs.update(
                                    matiere=form.cleaned_data.get('matiere'),
                                    heure_debut_cours=form.cleaned_data.get('heure_debut_cours'),
                                    heure_fin_cours=form.cleaned_data.get('heure_fin_cours'),
                                    motif_absence_retard=form.cleaned_data.get('motif_absence_retard', ''),
                                    justificatif_fourni=form.cleaned_data.get('justificatif_fourni', False),
                                )
                            if created or any(getattr(presence, champ) != valeur for champ, valeur in valeurs.items()):
                                for champ, valeur in valeurs.items():
                                    setattr(presence, champ, valeur)
                                presence.enregistre_par = request.user
                                presence.save()
                                enregistres += 1
                    if enregistres:
                        messages.success(request, f"{enregistres} pointage(s) enregistrés pour {classe.nom_classe}.")
                    elif renseignes:
                        messages.info(request, "Aucun pointage modifié.")
                    else:
                        messages.warning(request, "Aucun pointage renseigné : aucune présence n'a été créée.")
                    return redirect('liste_classes')
                except IntegrityError:
                    messages.error(request, "Le pointage a changé pendant la saisie. Rechargez la page.")
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        formset = PresenceFormSet(initial=initial_data, form_kwargs=form_kwargs)

    toutes_les_classes = Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active)
    if is_teacher_account(request.user):
        toutes_les_classes = toutes_les_classes.filter(
            pk__in=assigned_programs(request.user, ecole, annee_active).values('classe_id')
        )
    return render(request, 'dashboard/presences/marquer_presence_classe.html', {
        'classe': classe,
        'date_aujourdhui': date_aujourdhui,
        'formset': formset,
        'annee_active': annee_active,
        'toutes_les_classes': toutes_les_classes.order_by('nom_classe'),
    })


@school_role_required('school_admin', 'director', 'teacher')
def liste_presences(request):
    ecole = get_user_ecole(request)
    if not ecole:
        return HttpResponse('Aucune école associée à ce compte.', status=403)

    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.warning(request, "Aucune année scolaire active définie pour votre école.")
        return redirect('dashboard_accueil')

    classes = Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).order_by('nom_classe')
    if is_teacher_account(request.user):
        classes = classes.filter(pk__in=assigned_programs(request.user, ecole, annee_active).values('classe_id'))

    classe = None
    classe_id = request.GET.get('classe')
    if classe_id:
        classe = get_object_or_404(classes, pk=classe_id)
        if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, classe.pk, year=annee_active):
            return HttpResponse('Vous n’êtes pas affecté à cette classe.', status=403)

    date_filtre = request.GET.get('date')
    presences = Presence.objects.filter(ecole=ecole, annee_scolaire=annee_active, classe__in=classes)
    if classe:
        presences = presences.filter(classe=classe)
    if date_filtre:
        try:
            date_obj = datetime.strptime(date_filtre, '%Y-%m-%d').date()
            presences = presences.filter(date=date_obj)
        except ValueError:
            messages.warning(request, "La date sélectionnée est invalide.")
            date_filtre = ''

    absences_statut_absent = presences.filter(statut='Absent').count()
    absences_excusees = presences.filter(statut='Excusé').count()
    context = {
        'presences': presences.select_related('etudiant', 'classe').order_by('date', 'etudiant__nom'),
        'classes': classes,
        'classe_selectionnee': classe,
        'date_filtre': date_filtre,
        'annee_active': annee_active,
        'total_absences': absences_statut_absent + absences_excusees,
        'absences_statut_absent': absences_statut_absent,
        'absences_excusees': absences_excusees,
    }
    return render(request, 'dashboard/presences/liste_presences.html', context)




# ==========================
# Suivi des présences
# ==========================


@school_role_required('school_admin', 'director', 'teacher')
def suivi_presence_classe(request, classe_id):
    """
    Vue de suivi des présences d'une classe, filtrée strictement par l'école de l'utilisateur connecté.
    """
    # 🔹 Récupération de l'école de l'utilisateur
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Classe filtrée par l'école de l'utilisateur
    classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole)

    # 🔹 Année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre école.")
        return redirect('liste_annees_scolaires')
    if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, classe.pk, year=annee_active):
        return HttpResponse('Vous n’êtes pas affecté à cette classe.', status=403)

    # 🔹 Filtre par date optionnel
    date_filtre = request.GET.get('date')
    if date_filtre:
        try:
            date_filtre = datetime.strptime(date_filtre, '%Y-%m-%d').date()
        except ValueError:
            date_filtre = None

    # 🔹 Étudiants inscrits dans cette classe et cette école pour l'année active
    etudiants = Etudiant.objects.filter(
        ecole=ecole, inscriptions__classe=classe,
        inscriptions__annee_scolaire=annee_active, inscriptions__statut='active'
    ).order_by('nom', 'prenom')

    # Une ligne « Excusé » est une absence excusée, pas une présence.
    pointages_classe = Presence.objects.filter(
        classe=classe, annee_scolaire=annee_active, ecole=ecole,
        etudiant__in=etudiants,
    )
    if date_filtre:
        pointages_classe = pointages_classe.filter(date=date_filtre)
    absences_statut_absent = pointages_classe.filter(statut='Absent').count()
    absences_excusees = pointages_classe.filter(statut='Excusé').count()

    # 🔹 Présences par étudiant
    presences_par_etudiant = {}
    for etudiant in etudiants:
        presences_query = Presence.objects.filter(
            etudiant=etudiant,
            classe=classe,
            annee_scolaire=annee_active,
            ecole=ecole
        )
        if date_filtre:
            presences_query = presences_query.filter(date=date_filtre)
        presences_par_etudiant[etudiant] = presences_query.order_by('-date')

    # 🔹 Contexte
    context = {
        'classe': classe,
        'presences_par_etudiant': presences_par_etudiant,
        'date_filtre': date_filtre,
        'annee_active': annee_active,
        'toutes_les_classes': Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).order_by('nom_classe'),
        'total_absences': absences_statut_absent + absences_excusees,
        'absences_statut_absent': absences_statut_absent,
        'absences_excusees': absences_excusees,
    }

    return render(request, 'dashboard/presences/suivi_presence_classe.html', context)


@school_role_required('school_admin', 'director', 'teacher')
def suivi_presence_eleve(request, etudiant_id):
    """
    Suivi des présences d'un élève, filtré strictement par l'école de l'utilisateur connecté.
    """
    # 🔹 Récupération de l'école de l'utilisateur
    ecole_utilisateur = get_user_ecole(request)
    if not ecole_utilisateur:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Vérification : l'élève appartient bien à l'école de l'utilisateur
    etudiant = get_object_or_404(
        Etudiant.objects.all(),
        pk=etudiant_id,
        ecole=ecole_utilisateur
    )

    # 🔹 Année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(
        ecole=ecole_utilisateur,
        active=True
    ).first()

    if not annee_active:
        messages.warning(request, "Aucune année scolaire active n'est définie pour votre école.")
        return redirect('liste_annees_scolaires')

    inscription_courante = etudiant.inscriptions.filter(
        ecole=ecole_utilisateur, annee_scolaire=annee_active,
    ).select_related('classe').first()
    inscription = inscription_courante if inscription_courante and inscription_courante.statut == 'active' else None
    if is_teacher_account(request.user) and (not inscription or not teacher_can_teach(request.user, ecole_utilisateur, inscription.classe_id, year=annee_active)):
        return HttpResponse('Vous n’êtes pas affecté à la classe de cet élève.', status=403)

    # 🔹 Présences filtrées par élève, école et année scolaire
    presences = Presence.objects.filter(
        etudiant=etudiant,
        ecole=ecole_utilisateur,
        annee_scolaire=annee_active
    )
    if is_teacher_account(request.user) and inscription:
        presences = presences.filter(classe=inscription.classe)
    presences = presences.order_by('-date')

    # « Excusé » est une absence excusée dans les anciennes lignes.
    absences_statut_absent = presences.filter(statut='Absent').count()
    absences_excusees = presences.filter(statut='Excusé').count()
    stats = {
        'total_presents': presences.filter(statut='Présent').count(),
        'total_absents': absences_statut_absent + absences_excusees,
        'total_absents_statut_absent': absences_statut_absent,
        'total_retards': presences.filter(statut='Retard').count(),
        'total_excuses': absences_excusees,
    }

    # 🔹 Rendu
    context = {
        'etudiant': etudiant,
        'inscription_courante': inscription_courante,
        'presences': presences,
        **stats,
        'annee_active': annee_active,
    }

    return render(request, 'dashboard/presences/suivi_presence_eleve.html', context)

# ==========================
# Emplois du temps
# ==========================
# 🔹 LISTE DES EMPLOIS DU TEMPS (FILTRÉ PAR ÉCOLE)
# ==========================
