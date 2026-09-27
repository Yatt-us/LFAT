"""Parcours d'appel par séance, séparé du registre journalier historique."""

from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.forms import formset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dashboard.access import is_teacher_account, school_role_required
from dashboard.models import AnneeScolaire, EcoleSettings, Inscription
from dashboard.tenant import school_for_user
from parcours_scolaire.models import AffectationClasse
from .forms import DecisionForm, JustificationForm, PointageLigneForm, SeanceForm
from .models import Justification, Pointage, Seance


def _seances_visibles(request):
    ecole = school_for_user(request.user)
    queryset = Seance.objects.filter(
        ecole=ecole, classe__ecole=ecole, programme__ecole=ecole, enseignant__ecole=ecole,
    ).select_related(
        'classe', 'classe__annee_scolaire', 'programme__matiere', 'enseignant',
    )
    if is_teacher_account(request.user) and not request.user.is_superuser:
        enseignant = getattr(request.user, 'enseignant', None)
        queryset = queryset.filter(enseignant=enseignant, programme__enseignant=enseignant)
    return queryset


@school_role_required('school_admin', 'director', 'teacher')
def liste_seances(request):
    ecole = school_for_user(request.user)
    annee = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    seances = _seances_visibles(request)
    if annee:
        seances = seances.filter(classe__annee_scolaire=annee)
    else:
        seances = seances.none()
    date_filtre = request.GET.get('date', '')
    if date_filtre:
        try:
            seances = seances.filter(date=date.fromisoformat(date_filtre))
        except ValueError:
            messages.warning(request, 'La date saisie est invalide.')
            date_filtre = ''
    seances = seances.annotate(nb_pointages=Count('pointages'))
    peut_creer = request.user.is_superuser or getattr(
        getattr(request.user, 'profile', None), 'role', None,
    ) in {'school_admin', 'director'}
    return render(request, 'vie_scolaire/liste_seances.html', {
        'seances': seances, 'annee': annee, 'date_filtre': date_filtre, 'peut_creer': peut_creer,
    })


@school_role_required('school_admin', 'director')
def creer_seance(request):
    ecole = school_for_user(request.user)
    annee = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee:
        messages.warning(request, 'Activez une année scolaire avant de créer une séance.')
        return redirect('liste_annees_scolaires')
    form = SeanceForm(
        request.POST if request.method == 'POST' else None,
        ecole=ecole, annee_scolaire=annee,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                EcoleSettings.objects.select_for_update().get(pk=ecole.pk)
                seance = form.save(commit=False)
                seance.cree_par = request.user
                seance.save()
            messages.success(request, 'Séance créée. Vous pouvez faire l’appel.')
            return redirect('vie_scolaire:pointage_seance', seance_id=seance.pk)
        except (ValidationError, IntegrityError):
            form.add_error(None, 'La séance entre en conflit avec une autre. Rechargez le formulaire.')
    return render(request, 'vie_scolaire/creer_seance.html', {'form': form, 'annee': annee})


@school_role_required('school_admin', 'director', 'teacher')
def pointage_seance(request, seance_id):
    seance = get_object_or_404(_seances_visibles(request), pk=seance_id)
    affectations_a_la_date = AffectationClasse.objects.filter(
        inscription_id=OuterRef('pk'), classe=seance.classe,
        date_debut__lte=seance.date,
    ).filter(Q(date_fin__gt=seance.date) | Q(date_fin__isnull=True))
    inscriptions = list(Inscription.objects.filter(
        ecole=seance.ecole, annee_scolaire=seance.classe.annee_scolaire,
        date_inscription__lte=seance.date, etudiant__ecole=seance.ecole,
    ).annotate(affecte_a_la_date=Exists(affectations_a_la_date)).filter(
        Q(affecte_a_la_date=True) | Q(pointages_seance__seance=seance),
    ).distinct().select_related('etudiant').order_by('etudiant__nom', 'etudiant__prenom', 'pk'))
    inscription_ids = [inscription.pk for inscription in inscriptions]
    pointages = Pointage.objects.filter(
        seance=seance, inscription_id__in=inscription_ids,
    ).select_related('justification')
    existants = {pointage.inscription_id: pointage for pointage in pointages}
    initial = []
    for inscription in inscriptions:
        pointage = existants.get(inscription.pk)
        justification = getattr(pointage, 'justification', None) if pointage else None
        initial.append({
            'inscription': inscription,
            'eleve': inscription.etudiant,
            'statut': pointage.statut if pointage else '',
            'minutes_retard': pointage.minutes_retard if pointage else None,
            'pointage_id': pointage.pk if pointage else None,
            'justification': justification,
        })
    LigneSet = formset_factory(
        PointageLigneForm, extra=0, max_num=len(inscriptions), validate_max=True,
    )
    formset = LigneSet(
        request.POST if request.method == 'POST' else None,
        initial=initial,
        form_kwargs={'inscriptions': Inscription.objects.filter(pk__in=inscription_ids)},
    )
    if request.method == 'POST' and formset.is_valid():
        ids_soumis = [form.cleaned_data['inscription'].pk for form in formset]
        if ids_soumis != inscription_ids:
            messages.error(request, "La liste des élèves a changé. Rechargez l'appel.")
        else:
            for form in formset:
                donnees = form.cleaned_data
                pointage = existants.get(donnees['inscription'].pk)
                if (pointage and getattr(pointage, 'justification', None) and donnees['statut'] and
                        (pointage.statut != donnees['statut'] or
                         pointage.minutes_retard != donnees['minutes_retard'])):
                    form.add_error('statut', 'Une justification existe pour ce pointage. La correction doit être revue par la direction.')
            if not any(form.errors for form in formset):
                try:
                    modifies = 0
                    renseignes = 0
                    with transaction.atomic():
                        for form in formset:
                            donnees = form.cleaned_data
                            statut = donnees['statut']
                            if not statut:
                                continue
                            renseignes += 1
                            inscription = donnees['inscription']
                            minutes = donnees['minutes_retard'] if statut == Pointage.Statut.RETARD else None
                            pointage = existants.get(inscription.pk)
                            if pointage is None:
                                Pointage.objects.create(
                                    seance=seance, inscription=inscription, statut=statut,
                                    minutes_retard=minutes, saisi_par=request.user,
                                )
                                modifies += 1
                            elif pointage.statut != statut or pointage.minutes_retard != minutes:
                                pointage.statut = statut
                                pointage.minutes_retard = minutes
                                pointage.saisi_par = request.user
                                pointage.save()
                                modifies += 1
                    if modifies:
                        messages.success(request, f'{modifies} pointage(s) enregistrés.')
                    elif renseignes:
                        messages.info(request, 'Aucun pointage modifié.')
                    else:
                        messages.warning(request, "Aucun pointage renseigné : aucune présence n'a été créée.")
                    return redirect('vie_scolaire:pointage_seance', seance_id=seance.pk)
                except (ValidationError, IntegrityError):
                    messages.error(request, "Le pointage a changé pendant la saisie. Rechargez l'appel.")
    elif request.method == 'POST':
        messages.error(request, 'Corrigez les erreurs de pointage indiquées.')

    compteurs = {statut: 0 for statut in Pointage.Statut.values}
    for ligne in Pointage.objects.filter(
        seance=seance, inscription_id__in=inscription_ids,
    ).values('statut').annotate(total=Count('pk')):
        compteurs[ligne['statut']] = ligne['total']
    non_pointes = max(0, len(inscriptions) - sum(compteurs.values()))
    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    peut_decider = request.user.is_superuser or role in {'school_admin', 'director'}
    return render(request, 'vie_scolaire/pointage_seance.html', {
        'seance': seance, 'formset': formset, 'total_eleves': len(inscriptions),
        'presents': compteurs[Pointage.Statut.PRESENT],
        'absents': compteurs[Pointage.Statut.ABSENT],
        'retards': compteurs[Pointage.Statut.RETARD],
        'non_pointes': non_pointes, 'peut_decider': peut_decider,
    })


@school_role_required('school_admin', 'director', 'teacher')
def justifier_pointage(request, pointage_id):
    pointage = get_object_or_404(
        Pointage.objects.select_related('seance__classe', 'inscription__etudiant'),
        pk=pointage_id, seance__in=_seances_visibles(request),
    )
    if pointage.statut not in {Pointage.Statut.ABSENT, Pointage.Statut.RETARD}:
        return HttpResponseForbidden('Seule une absence ou un retard peut être justifié.')
    justification = Justification.objects.filter(pointage=pointage).first()
    if justification and justification.etat != Justification.Etat.ATTENTE:
        return HttpResponseForbidden('Cette justification a déjà reçu une décision.')
    form = JustificationForm(request.POST if request.method == 'POST' else None, instance=justification)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                document = form.save(commit=False)
                document.pointage = pointage
                if not document.pk:
                    document.soumis_par = request.user
                document.save()
            messages.success(request, 'Motif enregistré, en attente de décision.')
            return redirect('vie_scolaire:pointage_seance', seance_id=pointage.seance_id)
        except (ValidationError, IntegrityError):
            form.add_error(None, 'Le motif n’a pas pu être enregistré. Rechargez la page.')
    return render(request, 'vie_scolaire/justifier_pointage.html', {
        'form': form, 'pointage': pointage, 'justification': justification,
    })


@school_role_required('school_admin', 'director')
def decider_justification(request, justification_id):
    ecole = school_for_user(request.user)
    justification = get_object_or_404(
        Justification.objects.select_related('pointage__seance__classe', 'pointage__inscription__etudiant'),
        pk=justification_id, pointage__seance__ecole=ecole,
    )
    form = DecisionForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            justification = Justification.objects.select_for_update().get(pk=justification.pk)
            if justification.etat != Justification.Etat.ATTENTE:
                messages.warning(request, 'Une décision a déjà été enregistrée.')
            else:
                justification.etat = form.cleaned_data['decision']
                justification.commentaire_decision = form.cleaned_data['commentaire_decision']
                justification.decide_par = request.user
                justification.decide_le = timezone.now()
                justification.save()
                messages.success(request, 'Décision enregistrée. Le statut du pointage reste inchangé.')
        return redirect('vie_scolaire:pointage_seance', seance_id=justification.pointage.seance_id)
    return render(request, 'vie_scolaire/decider_justification.html', {
        'justification': justification, 'form': form,
    })
