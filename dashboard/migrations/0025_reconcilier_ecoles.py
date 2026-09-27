"""Repair legacy tenant ids only when all related records identify one school."""
from decimal import Decimal

from django.db import migrations


RELATIONS = {
    'Classe': ('annee_scolaire', 'enseignant_principal'),
    'Etudiant': ('annee_scolaire_inscription', 'classe'),
    'ProgrammeMatiere': ('classe', 'classe.annee_scolaire', 'matiere', 'enseignant'),
    'Inscription': ('etudiant', 'annee_scolaire', 'classe'),
    'DossierInscriptionImage': ('etudiant',),
    'Note': ('etudiant', 'annee_scolaire', 'matiere'),
    'CreanceScolaire': ('etudiant', 'annee_scolaire'),
    'Paiement': ('etudiant', 'annee_scolaire', 'creance'),
    'Presence': ('etudiant', 'annee_scolaire', 'classe', 'matiere'),
    'CertificatFrequentation': ('etudiant', 'annee_scolaire'),
    'EmploiDuTemps': ('classe', 'annee_scolaire', 'matiere', 'enseignant'),
}


def school_id_from(instance, relation):
    value = instance
    for name in relation.split('.'):
        value = getattr(value, name, None)
        if value is None:
            return None
    return value.ecole_id


def reconcile_school_ids(apps, schema_editor):
    db = schema_editor.connection.alias
    proposed = []
    for model_name, relations in RELATIONS.items():
        model = apps.get_model('dashboard', model_name)
        related = sorted(set(relation.replace('.', '__') for relation in relations))
        for row in model.objects.using(db).select_related(*related).iterator(chunk_size=1000):
            candidates = {school_id_from(row, relation) for relation in relations}
            candidates.discard(None)
            if len(candidates) != 1:
                raise RuntimeError(
                    f'{model_name} #{row.pk}: écoles parentes contradictoires ou absentes ({sorted(candidates)}). '
                    'Corrigez cette ligne avant de relancer la migration.'
                )
            expected = candidates.pop()
            if row.ecole_id != expected:
                proposed.append((model, row.pk, expected))
    for model, pk, expected in proposed:
        model.objects.using(db).filter(pk=pk).update(ecole_id=expected)


def attach_skipped_payments(apps, schema_editor):
    """Reattach the payments that 0023 correctly skipped before tenant repair."""
    payment_model = apps.get_model('dashboard', 'Paiement')
    due_model = apps.get_model('dashboard', 'CreanceScolaire')
    db = schema_editor.connection.alias
    keys = set(payment_model.objects.using(db).filter(creance_id=None).values_list(
        'ecole_id', 'etudiant_id', 'annee_scolaire_id', 'motif_paiement',
    ))
    for ecole_id, student_id, year_id, motif in sorted(keys):
        rows = list(payment_model.objects.using(db).filter(
            ecole_id=ecole_id, etudiant_id=student_id,
            annee_scolaire_id=year_id, motif_paiement=motif,
        ))
        candidates = list(due_model.objects.using(db).filter(
            ecole_id=ecole_id, etudiant_id=student_id,
            annee_scolaire_id=year_id, motif=motif,
            origine_historique=True,
        ).order_by('pk'))
        if len(candidates) > 1:
            raise RuntimeError(f'Plusieurs créances historiques pour l’élève #{student_id}, année #{year_id}, motif {motif}.')
        declared = [row.montant_du for row in rows if row.montant_du is not None and row.montant_du > 0]
        due = max(declared, default=Decimal('0.00'))
        paid = sum((row.montant or Decimal('0.00') for row in rows if not row.annule), Decimal('0.00'))
        uncertain = (
            not declared or len(set(declared)) > 1
            or any(row.montant_du is None or row.montant_du <= 0 for row in rows)
            or paid > due
        )
        if candidates:
            creance = candidates[0]
            if creance.montant_du != due or creance.a_verifier != uncertain:
                due_model.objects.using(db).filter(pk=creance.pk).update(
                    montant_du=due, a_verifier=uncertain,
                )
        else:
            creance = due_model.objects.using(db).create(
                ecole_id=ecole_id, etudiant_id=student_id,
                annee_scolaire_id=year_id, motif=motif,
                libelle='Reprise des paiements antérieurs', montant_du=due,
                origine_historique=True, a_verifier=uncertain,
            )
        payment_model.objects.using(db).filter(pk__in=[row.pk for row in rows if row.creance_id is None]).update(
            creance_id=creance.pk,
        )


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0024_private_media')]

    operations = [
        migrations.RunPython(reconcile_school_ids, migrations.RunPython.noop),
        migrations.RunPython(attach_skipped_payments, migrations.RunPython.noop),
    ]
