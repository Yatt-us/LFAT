"""Formulaire des règles annuelles de bulletin propres à chaque école."""
from decimal import Decimal

from django import forms

from .models import AnneeScolaire, RegleBulletinAnnuel


class RegleBulletinAnnuelForm(forms.ModelForm):
    class Meta:
        model = RegleBulletinAnnuel
        fields = (
            'annee_scolaire', 'cycle',
            'poids_trimestre_1', 'poids_trimestre_2', 'poids_trimestre_3',
        )
        widgets = {
            'annee_scolaire': forms.Select(attrs={'class': 'form-select'}),
            'cycle': forms.Select(attrs={'class': 'form-select'}),
            'poids_trimestre_1': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'poids_trimestre_2': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'poids_trimestre_3': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, ecole, **kwargs):
        super().__init__(*args, **kwargs)
        self.ecole = ecole
        self.instance.ecole = ecole
        self.fields['annee_scolaire'].queryset = AnneeScolaire.objects.filter(ecole=ecole).order_by('-annee')
        self.fields['annee_scolaire'].empty_label = 'Choisir une année scolaire'
        self.fields['cycle'].choices = [('', 'Choisir un cycle'), *RegleBulletinAnnuel.CYCLE_CHOICES]
        if self.instance.pk:
            self.fields['annee_scolaire'].disabled = True
            self.fields['cycle'].disabled = True

    def clean(self):
        cleaned = super().clean()
        annee = cleaned.get('annee_scolaire')
        cycle = cleaned.get('cycle')
        if annee and annee.ecole_id != self.ecole.pk:
            self.add_error('annee_scolaire', "Cette année n'appartient pas à votre école.")
        if annee and cycle and RegleBulletinAnnuel.objects.filter(
            ecole=self.ecole, annee_scolaire=annee, cycle=cycle,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error(None, 'Une règle existe déjà pour ce cycle et cette année.')
        poids = [cleaned.get(f'poids_trimestre_{numero}') for numero in (1, 2, 3)]
        if all(valeur is not None for valeur in poids) and sum(poids, Decimal('0')) <= 0:
            self.add_error(None, 'La somme des trois poids doit être strictement positive.')
        return cleaned
