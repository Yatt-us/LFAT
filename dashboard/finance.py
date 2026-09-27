"""Calculs financiers fondés sur les créances et les encaissements non annulés."""

from decimal import Decimal

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .models import CreanceScolaire


MONTANT = DecimalField(max_digits=12, decimal_places=2)


def creances_avec_total(ecole, annee_scolaire, etudiant=None):
    queryset = CreanceScolaire.objects.filter(
        ecole=ecole, annee_scolaire=annee_scolaire, etudiant__ecole=ecole,
    )
    if etudiant is not None:
        queryset = queryset.filter(etudiant=etudiant)
    return queryset.annotate(
        total_paye_calcule=Coalesce(
            Sum('paiements__montant', filter=Q(paiements__annule=False)),
            Value(Decimal('0.00')), output_field=MONTANT,
        ),
    )


import hashlib
from datetime import date
from django.utils import timezone


def detecter_remise_fratrie(etudiant):
    """Calcule la remise fratrie applicable selon le rang de naissance de l'enfant dans l'école.

    Barème usuel des écoles privées de Bamako :
    - 1er enfant : 0% (plein tarif)
    - 2ème enfant : 10%
    - 3ème enfant et plus : 20%
    """
    fratrie = list(etudiant.fratrie())
    if not fratrie:
        return 'aucune', Decimal('0.00')

    tous_enfants = sorted([etudiant] + fratrie, key=lambda e: (e.date_naissance or date.min, e.pk))
    index_enfant = tous_enfants.index(etudiant)

    if index_enfant == 0:
        return 'aucune', Decimal('0.00')
    elif index_enfant == 1:
        return 'fratrie', Decimal('10.00')
    else:
        return 'fratrie', Decimal('20.00')


def generer_recu_securise(paiement):
    """Génère un code de reçu inviolable basé sur une empreinte SHA-256."""
    raw = f"{paiement.ecole_id}-{paiement.pk}-{paiement.montant}-{paiement.date_paiement}"
    hash_part = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8].upper()
    code = f"REC-{paiement.ecole_id}-{paiement.pk}-{hash_part}"
    if paiement.recu_code_securise != code:
        paiement.recu_code_securise = code
        paiement.save(update_fields=['recu_code_securise'])
    return code


def statistiques_recouvrement_ecole(ecole, annee_scolaire):
    """Fournit les statistiques de facturation et de recouvrement de l'établissement."""
    creances = creances_avec_total(ecole, annee_scolaire)
    total_brut = creances.aggregate(tot=Sum('montant_du'))['tot'] or Decimal('0.00')
    total_remises = creances.aggregate(tot=Sum('remise_montant'))['tot'] or Decimal('0.00')
    total_net = max(Decimal('0.00'), total_brut - total_remises)
    total_recouvre = sum((c.total_paye_calcule for c in creances), Decimal('0.00'))
    taux_recouvrement = (
        (total_recouvre / total_net * 100).quantize(Decimal('0.01')) if total_net > 0 else Decimal('0.00')
    )
    return {
        'total_brut': total_brut,
        'total_remises': total_remises,
        'total_net': total_net,
        'total_recouvre': total_recouvre,
        'taux_recouvrement': taux_recouvrement,
    }


def echeances_en_retard(ecole, annee_scolaire):
    """Identifie les créances impayées ayant dépassé leur date limite d'exigibilité."""
    creances = creances_avec_total(ecole, annee_scolaire).filter(
        date_echeance__lt=timezone.localdate(),
    )
    return [c for c in creances if not c.est_soldee]
