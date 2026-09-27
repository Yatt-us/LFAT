from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('dashboard', '0020_inscription_annuelle')]

    operations = [
        migrations.AlterField(model_name='enseignant', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='enseignants', to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='classe', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='matiere', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='programmematiere', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='etudiant', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='dossierinscriptionimage', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='note', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='paiement', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='presence', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='certificatfrequentation', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='emploidutemps', name='ecole', field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dashboard.ecolesettings', verbose_name='École')),
        migrations.AlterField(model_name='matiere', name='nom', field=models.CharField(max_length=100, verbose_name='Nom de la Matière')),
        migrations.AlterField(model_name='matiere', name='code_matiere', field=models.CharField(blank=True, max_length=10, null=True, verbose_name='Code Matière')),
        migrations.AlterField(model_name='etudiant', name='numero_matricule', field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Numéro Matricule')),
        migrations.AlterField(model_name='note', name='valeur', field=models.DecimalField(decimal_places=2, max_digits=4, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(20)], verbose_name='Note Obtenue (sur 20)')),
        migrations.AlterUniqueTogether(name='presence', unique_together=set()),
        migrations.AddConstraint(model_name='matiere', constraint=models.UniqueConstraint(fields=('ecole', 'nom'), name='uniq_matiere_nom_par_ecole')),
        migrations.AddConstraint(model_name='matiere', constraint=models.UniqueConstraint(condition=Q(code_matiere__isnull=False) & ~Q(code_matiere=''), fields=('ecole', 'code_matiere'), name='uniq_matiere_code_par_ecole')),
        migrations.AddConstraint(model_name='etudiant', constraint=models.UniqueConstraint(condition=Q(numero_matricule__isnull=False) & ~Q(numero_matricule=''), fields=('ecole', 'numero_matricule'), name='uniq_matricule_par_ecole')),
        migrations.AddConstraint(model_name='presence', constraint=models.UniqueConstraint(fields=('etudiant', 'classe', 'date', 'annee_scolaire'), name='uniq_presence_par_classe_et_jour')),
    ]
