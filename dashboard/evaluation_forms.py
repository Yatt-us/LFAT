"""Formulaires des évaluations distinctes des anciennes notes trimestrielles."""

from django import forms
from django.utils import timezone

from .access import assigned_programs, is_teacher_account
from .models import Evaluation, ProgrammeMatiere


class EvaluationForm(forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = [
            'programme', 'periode_evaluation', 'titre', 'type_evaluation',
            'date_evaluation', 'bareme', 'poids',
        ]
        widgets = {
            'programme': forms.Select(attrs={'class': 'form-select'}),
            'periode_evaluation': forms.Select(attrs={'class': 'form-select'}),
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'type_evaluation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Devoir, interrogation, composition…'}),
            'date_evaluation': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'bareme': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'poids': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
        }

    def __init__(self, *args, ecole, annee_scolaire, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.ecole = ecole
        programmes = ProgrammeMatiere.objects.filter(
            ecole=ecole, classe__ecole=ecole, classe__annee_scolaire=annee_scolaire,
        ).select_related('classe', 'matiere').order_by('classe__nom_classe', 'matiere__nom')
        if is_teacher_account(user):
            programmes = programmes.filter(pk__in=assigned_programs(user, ecole, annee_scolaire).values('pk'))
        self.fields['programme'].queryset = programmes
        self.fields['date_evaluation'].initial = timezone.localdate()


class SaisieResultatsForm(forms.Form):
    """Une note et une action d’annulation par inscription."""

    def __init__(self, *args, evaluation, inscriptions, existants=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inscriptions = list(inscriptions)
        existants = existants or {}
        for inscription in self.inscriptions:
            self.fields[f'note_{inscription.pk}'] = forms.DecimalField(
                required=False, min_value=0, max_value=evaluation.bareme,
                max_digits=6, decimal_places=2,
                initial=(existants[inscription.pk].valeur
                         if inscription.pk in existants and not existants[inscription.pk].annule else None),
                label=f'{inscription.etudiant.prenom} {inscription.etudiant.nom}',
                widget=forms.NumberInput(attrs={
                    'class': 'form-control', 'min': '0',
                    'max': str(evaluation.bareme), 'step': '0.01',
                    'aria-label': f'Note de {inscription.etudiant.prenom} {inscription.etudiant.nom}',
                }),
            )
            self.fields[f'effacer_{inscription.pk}'] = forms.BooleanField(
                required=False, label='Effacer ce résultat',
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            )
