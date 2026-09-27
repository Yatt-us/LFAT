from decimal import Decimal
from itertools import groupby
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def reprendre_frais_historiques(apps, schema_editor):
    Paiement = apps.get_model('dashboard', 'Paiement')
    Creance = apps.get_model('dashboard', 'CreanceScolaire')
    db = schema_editor.connection.alias
    payments = (
        Paiement.objects.using(db)
        .select_related('etudiant', 'annee_scolaire')
        .order_by('ecole_id', 'etudiant_id', 'annee_scolaire_id', 'motif_paiement', 'pk')
        .iterator(chunk_size=1000)
    )
    key = lambda p: (p.ecole_id, p.etudiant_id, p.annee_scolaire_id, p.motif_paiement)
    for (ecole_id, etudiant_id, annee_id, motif), group in groupby(payments, key=key):
        rows = list(group)
        # Les relations incohérentes restent visibles dans les anciens paiements,
        # mais ne doivent pas devenir une créance d'une autre école.
        if rows[0].etudiant.ecole_id != ecole_id or rows[0].annee_scolaire.ecole_id != ecole_id:
            continue
        declared = [p.montant_du for p in rows if p.montant_du is not None and p.montant_du > 0]
        paid = sum((p.montant or Decimal('0.00') for p in rows), Decimal('0.00'))
        due = max(declared, default=Decimal('0.00'))
        uncertain = (
            not declared or len(set(declared)) > 1
            or any(p.montant_du is None or p.montant_du <= 0 for p in rows)
            or paid > due
        )
        creance = Creance.objects.using(db).create(
            ecole_id=ecole_id, etudiant_id=etudiant_id, annee_scolaire_id=annee_id,
            motif=motif, libelle='Reprise des paiements antérieurs',
            montant_du=due, origine_historique=True, a_verifier=uncertain,
        )
        Paiement.objects.using(db).filter(pk__in=[p.pk for p in rows]).update(creance_id=creance.pk)


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0022_annee_active_unique'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CreanceScolaire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('motif', models.CharField(choices=[('Frais de Scolarité', 'Frais de Scolarité'), ("Frais d'Inscription", "Frais d'Inscription"), ('Cotisation APEM', 'Cotisation APEM'), ('Tenue Scolaire', 'Tenue Scolaire'), ('Repas Scolaire', 'Repas Scolaire'), ('Autres', 'Autres')], max_length=100)),
                ('libelle', models.CharField(blank=True, max_length=200)),
                ('montant_du', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(Decimal('0.01'))])),
                ('origine_historique', models.BooleanField(default=False)),
                ('a_verifier', models.BooleanField(default=False, verbose_name='Montant historique à vérifier')),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='creances', to='dashboard.anneescolaire')),
                ('ecole', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='creances', to='dashboard.ecolesettings')),
                ('etudiant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='creances', to='dashboard.etudiant')),
            ],
            options={
                'verbose_name': 'Frais scolaire dû',
                'verbose_name_plural': 'Frais scolaires dus',
                'ordering': ['etudiant__nom', 'motif', 'pk'],
            },
        ),
        migrations.AddField(
            model_name='paiement', name='creance',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='paiements', to='dashboard.creancescolaire', verbose_name='Frais concerné'),
        ),
        migrations.AddField(
            model_name='paiement', name='annule',
            field=models.BooleanField(default=False, verbose_name='Paiement annulé'),
        ),
        migrations.AddField(
            model_name='paiement', name='annule_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='paiement', name='annule_par',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='paiements_annules', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='paiement', name='montant_du',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Montant dû historique'),
        ),
        migrations.RunPython(reprendre_frais_historiques, migrations.RunPython.noop),
    ]
