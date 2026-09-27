"""Réglages explicites de la pondération des bulletins annuels."""
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.access import school_role_required
from dashboard.bulletin_policy_forms import RegleBulletinAnnuelForm
from dashboard.models import AnneeScolaire, RegleBulletinAnnuel
from dashboard.tenant import school_for_user


@school_role_required('school_admin', 'director')
@require_http_methods(['GET'])
def liste_regles_bulletin_annuel(request):
    ecole = school_for_user(request.user)
    annees = list(AnneeScolaire.objects.filter(ecole=ecole).order_by('-active', '-annee'))
    regles = {
        (regle.annee_scolaire_id, regle.cycle): regle
        for regle in RegleBulletinAnnuel.objects.filter(ecole=ecole).select_related('valide_par')
    }
    groupes = [
        {
            'annee': annee,
            'cycles': [
                {'code': code, 'libelle': libelle, 'regle': regles.get((annee.pk, code))}
                for code, libelle in RegleBulletinAnnuel.CYCLE_CHOICES
            ],
        }
        for annee in annees
    ]
    return render(request, 'dashboard/bulletins/regles_bulletin_annuel.html', {'groupes': groupes})


def _formulaire_regle(request, regle=None):
    ecole = school_for_user(request.user)
    if regle is None:
        regle = RegleBulletinAnnuel(ecole=ecole)
    initial = {}
    if request.method == 'GET' and not regle.pk:
        annee = AnneeScolaire.objects.filter(ecole=ecole, pk=request.GET.get('annee')).first() if request.GET.get('annee', '').isdigit() else None
        cycle = request.GET.get('cycle')
        if annee:
            initial['annee_scolaire'] = annee.pk
        if cycle in dict(RegleBulletinAnnuel.CYCLE_CHOICES):
            initial['cycle'] = cycle
    form = RegleBulletinAnnuelForm(
        request.POST if request.method == 'POST' else None,
        instance=regle, ecole=ecole, initial=initial,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            form.add_error(None, 'Une règle existe déjà pour ce cycle et cette année.')
        else:
            messages.success(request, 'Règle enregistrée. Une validation de la direction est nécessaire avant son utilisation.')
            return redirect('liste_regles_bulletin_annuel')
    return render(request, 'dashboard/bulletins/form_regle_bulletin_annuel.html', {
        'form': form,
        'regle': regle if regle.pk else None,
    })


@school_role_required('school_admin', 'director')
@require_http_methods(['GET', 'POST'])
def creer_regle_bulletin_annuel(request):
    return _formulaire_regle(request)


@school_role_required('school_admin', 'director')
@require_http_methods(['GET', 'POST'])
def modifier_regle_bulletin_annuel(request, pk):
    regle = get_object_or_404(RegleBulletinAnnuel, pk=pk, ecole=school_for_user(request.user))
    return _formulaire_regle(request, regle)


@school_role_required('school_admin', 'director')
@require_POST
def valider_regle_bulletin_annuel(request, pk):
    with transaction.atomic():
        regle = get_object_or_404(
            RegleBulletinAnnuel.objects.select_for_update(),
            pk=pk, ecole=school_for_user(request.user),
        )
        if not regle.est_validee:
            regle.valide_par = request.user
            regle.valide_le = timezone.now()
            regle.save(update_fields={'valide_par', 'valide_le'})
            messages.success(request, 'Règle de bulletin annuel validée.')
        else:
            messages.info(request, 'Cette règle est déjà validée.')
    return redirect('liste_regles_bulletin_annuel')
