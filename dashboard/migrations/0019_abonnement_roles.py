from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_subscription_status(apps, schema_editor):
    EcoleSettings = apps.get_model('dashboard', 'EcoleSettings')
    Profile = apps.get_model('dashboard', 'Profile')
    Enseignant = apps.get_model('dashboard', 'Enseignant')
    now = timezone.now()
    for school in EcoleSettings.objects.all().iterator():
        if not school.est_active:
            school.statut_abonnement = 'suspended'
        elif school.date_fin_essai and school.date_fin_essai >= now:
            school.statut_abonnement = 'trial'
        else:
            # A legacy active flag is not evidence of a paid subscription.
            school.statut_abonnement = 'expired'
        school.save(update_fields=['statut_abonnement'])

    # Existing teacher accounts should not inherit the new admin role by default.
    teacher_user_ids = Enseignant.objects.exclude(user_id=None).values_list('user_id', flat=True)
    Profile.objects.filter(user_id__in=teacher_user_ids).update(role='teacher')


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0018_ecolesettings_date_fin_essai_and_more')]

    operations = [
        migrations.AddField(
            model_name='ecolesettings', name='statut_abonnement',
            field=models.CharField(choices=[('trial', 'Essai'), ('active', 'Actif'), ('expired', 'Expiré'), ('suspended', 'Suspendu')], default='trial', max_length=20),
        ),
        migrations.AddField(
            model_name='ecolesettings', name='date_fin_abonnement',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='profile', name='role',
            field=models.CharField(choices=[('school_admin', 'Administrateur'), ('director', 'Direction'), ('secretary', 'Secrétariat'), ('accountant', 'Comptabilité'), ('teacher', 'Enseignant')], default='school_admin', max_length=20),
        ),
        migrations.CreateModel(
            name='DemandeAbonnement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('montant', models.DecimalField(decimal_places=2, default=25000, max_digits=10)),
                ('mode_paiement', models.CharField(blank=True, max_length=50)),
                ('reference', models.CharField(blank=True, max_length=100)),
                ('statut', models.CharField(choices=[('pending', 'En attente'), ('paid', 'Payé'), ('rejected', 'Rejeté')], default='pending', max_length=20)),
                ('cree_le', models.DateTimeField(auto_now_add=True)),
                ('confirme_le', models.DateTimeField(blank=True, null=True)),
                ('ecole', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='demandes_abonnement', to='dashboard.ecolesettings')),
            ],
            options={'ordering': ['-cree_le'], 'verbose_name': 'Demande d’abonnement', 'verbose_name_plural': 'Demandes d’abonnement'},
        ),
        migrations.RunPython(backfill_subscription_status, migrations.RunPython.noop),
    ]
