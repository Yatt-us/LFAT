"""Synchronisation atomique de la classe courante et de son intervalle daté."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dashboard.models import Inscription
from .models import AffectationClasse


def synchroniser_affectation(inscription, *, date_effet=None, acteur=None):
    """Ferme l'ancienne affectation et ouvre la nouvelle à la date d'effet.

    La fin est exclusive. Une correction le jour même remplace le segment du jour
    seulement si aucun appel par séance ne repose déjà sur cette classe.
    """
    date_effet = date_effet or timezone.localdate()
    with transaction.atomic():
        courante = Inscription.objects.select_for_update().select_related(
            'classe', 'annee_scolaire',
        ).get(pk=inscription.pk)
        ouverte = AffectationClasse.objects.select_for_update().filter(
            inscription=courante, date_fin__isnull=True,
        ).first()
        nouvelle_classe = courante.classe if courante.statut == 'active' else None
        if ouverte and nouvelle_classe and ouverte.classe_id == nouvelle_classe.pk:
            return ouverte
        if ouverte:
            if date_effet < ouverte.date_debut:
                # Une préinscription encore future peut être corrigée avant son effet.
                from vie_scolaire.models import Pointage
                if (ouverte.date_debut <= timezone.localdate() or Pointage.objects.filter(
                    inscription=courante, seance__classe=ouverte.classe,
                    seance__date__gte=ouverte.date_debut,
                ).exists()):
                    raise ValidationError('La date de changement précède le début de l’affectation actuelle.')
                if nouvelle_classe:
                    ouverte.classe = nouvelle_classe
                    ouverte.origine = AffectationClasse.Origine.SAISIE
                    ouverte.cree_par = acteur
                    ouverte.save(update_fields=['classe', 'origine', 'cree_par'])
                    return ouverte
                ouverte.delete()
                return None
            if date_effet == ouverte.date_debut:
                from vie_scolaire.models import Pointage
                if Pointage.objects.filter(
                    inscription=courante, seance__classe=ouverte.classe,
                    seance__date=date_effet,
                ).exists():
                    raise ValidationError('Un appel existe déjà pour cette classe à cette date ; le changement nécessite une correction encadrée.')
                if nouvelle_classe:
                    precedente = AffectationClasse.objects.filter(
                        inscription=courante, classe=nouvelle_classe,
                        date_fin=date_effet,
                    ).exclude(pk=ouverte.pk).order_by('-date_debut').first()
                    if precedente:
                        ouverte.delete()
                        precedente.date_fin = None
                        precedente.termine_par = None
                        precedente.save(update_fields=['date_fin', 'termine_par'])
                        return precedente
                    ouverte.classe = nouvelle_classe
                    ouverte.origine = AffectationClasse.Origine.SAISIE
                    ouverte.cree_par = acteur
                    ouverte.save(update_fields=['classe', 'origine', 'cree_par'])
                    return ouverte
                ouverte.delete()
                return None
            ouverte.date_fin = date_effet
            ouverte.termine_par = acteur
            ouverte.save(update_fields=['date_fin', 'termine_par'])
        if nouvelle_classe:
            premiere_affectation = not AffectationClasse.objects.filter(inscription=courante).exists()
            date_debut = (
                max(date_effet, courante.annee_scolaire.date_debut, courante.date_inscription)
                if premiere_affectation else date_effet
            )
            if date_debut > courante.annee_scolaire.date_fin:
                raise ValidationError('La date de changement dépasse la fin de cette année scolaire.')
            precedente = AffectationClasse.objects.filter(
                inscription=courante, classe=nouvelle_classe, date_fin=date_debut,
            ).order_by('-date_debut').first()
            if precedente:
                precedente.date_fin = None
                precedente.termine_par = None
                precedente.save(update_fields=['date_fin', 'termine_par'])
                return precedente
            return AffectationClasse.objects.create(
                inscription=courante, classe=nouvelle_classe,
                date_debut=date_debut, origine=AffectationClasse.Origine.SAISIE,
                cree_par=acteur,
            )
        return None
