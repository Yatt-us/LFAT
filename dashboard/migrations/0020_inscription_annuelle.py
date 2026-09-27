from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def backfill_enrollments(apps, schema_editor):
    Student = apps.get_model('dashboard', 'Etudiant')
    Enrollment = apps.get_model('dashboard', 'Inscription')
    for student in Student.objects.select_related('classe', 'annee_scolaire_inscription').iterator():
        year_id = student.annee_scolaire_inscription_id
        class_id = student.classe_id
        if class_id:
            klass = student.classe
            if klass.ecole_id != student.ecole_id or klass.annee_scolaire_id != year_id:
                class_id = None
        status = {'Actif': 'active', 'Suspendu': 'suspendue', 'Ancien': 'terminee', 'Radié': 'transferee'}.get(student.statut, 'active')
        Enrollment.objects.get_or_create(
            etudiant_id=student.pk, annee_scolaire_id=year_id,
            defaults={
                'ecole_id': student.ecole_id, 'classe_id': class_id,
                'date_inscription': student.date_inscription, 'statut': status,
            },
        )


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0019_abonnement_roles')]

    operations = [
        migrations.CreateModel(
            name='Inscription',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_inscription', models.DateField(default=django.utils.timezone.localdate)),
                ('statut', models.CharField(choices=[('active', 'Active'), ('suspendue', 'Suspendue'), ('terminee', 'Terminée'), ('transferee', 'Transférée')], default='active', max_length=20)),
                ('annee_scolaire', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='inscriptions', to='dashboard.anneescolaire')),
                ('classe', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='inscriptions', to='dashboard.classe')),
                ('ecole', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscriptions', to='dashboard.ecolesettings')),
                ('etudiant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscriptions', to='dashboard.etudiant')),
            ],
            options={'verbose_name': 'Inscription annuelle', 'verbose_name_plural': 'Inscriptions annuelles', 'ordering': ['annee_scolaire__annee', 'classe__nom_classe', 'etudiant__nom'], 'unique_together': {('etudiant', 'annee_scolaire')}},
        ),
        migrations.RunPython(backfill_enrollments, migrations.RunPython.noop),
    ]
