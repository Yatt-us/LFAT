"""Création d'épreuves et saisie de plusieurs résultats sans écraser les anciennes notes."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from ..access import assigned_programs, is_teacher_account, school_role_required, teacher_can_teach
from ..evaluation_forms import EvaluationForm, SaisieResultatsForm
from ..models import AnneeScolaire, Evaluation, Inscription, Note, ResultatEvaluation
from ..tenant import school_for_user
from parcours_scolaire.models import AffectationClasse


@school_role_required('school_admin', 'director', 'teacher')
def liste_evaluations(request):
    ecole = school_for_user(request.user)
    annee = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    evaluations = Evaluation.objects.none()
    if annee:
        evaluations = Evaluation.objects.filter(
            ecole=ecole, programme__classe__annee_scolaire=annee,
        )
        if is_teacher_account(request.user):
            evaluations = evaluations.filter(
                programme__in=assigned_programs(request.user, ecole, annee)
            )
        evaluations = evaluations.select_related(
            'programme__classe', 'programme__matiere', 'cree_par'
        ).order_by('programme__classe__nom_classe', 'programme__matiere__nom', 'date_evaluation', 'pk')
    return render(request, 'dashboard/evaluations/liste.html', {
        'annee_active': annee, 'evaluations': evaluations,
    })


@school_role_required('school_admin', 'director', 'teacher')
def creer_evaluation(request):
    ecole = school_for_user(request.user)
    annee = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if annee is None:
        messages.error(request, 'Activez une année scolaire avant de créer une évaluation.')
        return redirect('liste_annees_scolaires')
    form = EvaluationForm(
        request.POST or None, ecole=ecole, annee_scolaire=annee, user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        evaluation = form.save(commit=False)
        programme = evaluation.programme
        if is_teacher_account(request.user) and not teacher_can_teach(
            request.user, ecole, programme.classe_id, programme.matiere_id, annee,
        ):
            return HttpResponseForbidden('Vous n’êtes pas affecté à cette matière.')
        notes_anciennes = Note.objects.filter(
            ecole=ecole, matiere=programme.matiere,
            annee_scolaire=annee, periode_evaluation=evaluation.periode_evaluation,
            etudiant__inscriptions__classe=programme.classe,
            etudiant__inscriptions__annee_scolaire=annee,
        )
        if notes_anciennes.exists():
            form.add_error(
                'programme',
                'Des notes anciennes existent pour cette classe, cette matière et cette période. '
                'Corrigez ou migrez ces notes avant de créer des évaluations détaillées.',
            )
        else:
            evaluation.ecole = ecole
            evaluation.cree_par = request.user
            evaluation.save()
            messages.success(request, 'Évaluation créée. Saisissez maintenant les résultats des élèves.')
            return redirect('saisir_resultats_evaluation', evaluation_id=evaluation.pk)
    return render(request, 'dashboard/evaluations/creer.html', {
        'form': form, 'annee_active': annee,
    })


@school_role_required('school_admin', 'director', 'teacher')
def saisir_resultats_evaluation(request, evaluation_id):
    ecole = school_for_user(request.user)
    annee = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    evaluation = get_object_or_404(
        Evaluation.objects.select_related('programme__classe', 'programme__matiere'),
        pk=evaluation_id, ecole=ecole, programme__classe__annee_scolaire=annee,
    )
    programme = evaluation.programme
    if is_teacher_account(request.user) and not teacher_can_teach(
        request.user, ecole, programme.classe_id, programme.matiere_id, annee,
    ):
        return HttpResponseForbidden('Vous n’êtes pas affecté à cette matière.')

    affectations_a_la_date = AffectationClasse.objects.filter(
        inscription_id=OuterRef('pk'), classe=programme.classe,
        date_debut__lte=evaluation.date_evaluation,
    ).filter(
        Q(date_fin__gt=evaluation.date_evaluation) | Q(date_fin__isnull=True),
    )
    inscriptions = list(Inscription.objects.filter(
        ecole=ecole, annee_scolaire=annee, etudiant__ecole=ecole,
        date_inscription__lte=evaluation.date_evaluation,
    ).annotate(
        affectee_a_la_date=Exists(affectations_a_la_date),
    ).filter(
        affectee_a_la_date=True,
    ).select_related('etudiant').order_by('etudiant__nom', 'etudiant__prenom'))
    existants = {
        resultat.inscription_id: resultat
        for resultat in ResultatEvaluation.objects.filter(
            evaluation=evaluation, inscription__in=inscriptions,
        )
    }
    form = SaisieResultatsForm(
        request.POST or None, evaluation=evaluation, inscriptions=inscriptions, existants=existants,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            changes = 0
            with transaction.atomic():
                for inscription in inscriptions:
                    valeur = form.cleaned_data[f'note_{inscription.pk}']
                    effacer = form.cleaned_data[f'effacer_{inscription.pk}']
                    resultat = existants.get(inscription.pk)
                    if effacer:
                        if resultat is not None and not resultat.annule:
                            resultat.annule = True
                            resultat.annule_le = timezone.now()
                            resultat.annule_par = request.user
                            resultat.modifie_par = request.user
                            resultat.save(update_fields=[
                                'annule', 'annule_le', 'annule_par', 'modifie_par', 'modifie_le',
                            ])
                            changes += 1
                        continue
                    if valeur is None:
                        continue
                    if resultat is None:
                        ResultatEvaluation.objects.create(
                            evaluation=evaluation, inscription=inscription, valeur=valeur,
                            saisi_par=request.user, modifie_par=request.user,
                        )
                        changes += 1
                    elif resultat.annule or resultat.valeur != valeur:
                        resultat.valeur = valeur
                        resultat.annule = False
                        resultat.annule_le = None
                        resultat.annule_par = None
                        resultat.modifie_par = request.user
                        resultat.save(update_fields=[
                            'valeur', 'annule', 'annule_le', 'annule_par', 'modifie_par', 'modifie_le',
                        ])
                        changes += 1
            messages.success(request, f'{changes} résultat(s) enregistré(s) ou corrigé(s).')
            return redirect('saisir_resultats_evaluation', evaluation_id=evaluation.pk)
        except ValidationError as exc:
            form.add_error(None, exc)
    rows = [
        {'inscription': inscription, 'field': form[f'note_{inscription.pk}'],
         'clear_field': form[f'effacer_{inscription.pk}'],
         'resultat': existants.get(inscription.pk)}
        for inscription in inscriptions
    ]
    return render(request, 'dashboard/evaluations/saisir_resultats.html', {
        'evaluation': evaluation, 'rows': rows, 'form': form,
        'annee_active': annee, 'retour_url': reverse('liste_evaluations'),
    })
