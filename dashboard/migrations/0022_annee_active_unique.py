from django.db import migrations, models
from django.db.models import Q


def keep_one_active_year(apps, schema_editor):
    AnneeScolaire = apps.get_model('dashboard', 'AnneeScolaire')
    school_ids = AnneeScolaire.objects.filter(active=True).values_list('ecole_id', flat=True).distinct()
    for school_id in school_ids.iterator():
        active_years = AnneeScolaire.objects.filter(ecole_id=school_id, active=True).order_by('-annee', '-pk')
        keep_id = active_years.values_list('pk', flat=True).first()
        active_years.exclude(pk=keep_id).update(active=False)


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0021_tenant_constraints')]

    operations = [
        migrations.RunPython(keep_one_active_year, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='anneescolaire',
            constraint=models.UniqueConstraint(condition=Q(active=True), fields=('ecole',), name='uniq_annee_active_par_ecole'),
        ),
    ]
