from django import forms
from django.utils import timezone

from dashboard.models import Inscription, ProgrammeMatiere
from .models import Justification, Pointage, Seance


class SeanceForm(forms.ModelForm):
    class Meta:
        model = Seance
        fields = ['programme', 'date', 'heure_debut', 'heure_fin']
        widgets = {
            'programme': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'heure_debut': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'heure_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def __init__(self, *args, ecole=None, annee_scolaire=None, **kwargs):
        self.ecole = ecole
        self.annee_scolaire = annee_scolaire
        super().__init__(*args, **kwargs)
        programmes = ProgrammeMatiere.objects.none()
        if ecole and annee_scolaire:
            programmes = ProgrammeMatiere.objects.filter(
                ecole=ecole, classe__ecole=ecole,
                classe__annee_scolaire=annee_scolaire,
                enseignant__ecole=ecole,
            ).select_related('classe', 'matiere', 'enseignant')
        self.fields['programme'].queryset = programmes
        self.fields['date'].initial = timezone.localdate()
        self.fields['programme'].label = 'Classe · matière · enseignant'
        self.fields['programme'].label_from_instance = (
            lambda p: f'{p.classe.nom_classe} · {p.matiere.nom} · {p.enseignant}'
        )

    def clean(self):
        cleaned = super().clean()
        programme = cleaned.get('programme')
        if programme and self.ecole and self.annee_scolaire:
            if programme.classe.annee_scolaire_id != self.annee_scolaire.pk:
                self.add_error('programme', "Le programme doit appartenir à l'année active.")
            self.instance.ecole = self.ecole
            self.instance.classe = programme.classe
            self.instance.enseignant = programme.enseignant
        return cleaned

    def save(self, commit=True):
        seance = super().save(commit=False)
        seance.ecole = self.ecole
        seance.classe = seance.programme.classe
        seance.enseignant = seance.programme.enseignant
        if commit:
            seance.save()
        return seance


class PointageLigneForm(forms.Form):
    inscription = forms.ModelChoiceField(queryset=Inscription.objects.none(), widget=forms.HiddenInput())
    statut = forms.ChoiceField(
        choices=[('', 'Non pointé')] + list(Pointage.Statut.choices), required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    minutes_retard = forms.IntegerField(
        required=False, min_value=1, max_value=1440, label='Minutes de retard',
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 1, 'placeholder': 'min'}),
    )

    def __init__(self, *args, inscriptions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['inscription'].queryset = inscriptions if inscriptions is not None else Inscription.objects.none()

    def clean(self):
        cleaned = super().clean()
        statut = cleaned.get('statut')
        minutes = cleaned.get('minutes_retard')
        if statut == Pointage.Statut.RETARD and minutes is None:
            self.add_error('minutes_retard', 'Indiquez les minutes de retard.')
        elif statut != Pointage.Statut.RETARD and minutes is not None:
            self.add_error('minutes_retard', 'Les minutes sont réservées au statut Retard.')
        return cleaned


class JustificationForm(forms.ModelForm):
    class Meta:
        model = Justification
        fields = ['motif']
        widgets = {
            'motif': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'maxlength': 2000}),
        }

    def clean_motif(self):
        motif = self.cleaned_data['motif'].strip()
        if not motif:
            raise forms.ValidationError('Saisissez un motif.')
        return motif


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[('', 'Choisir une décision'), (Justification.Etat.VALIDEE, 'Valider'),
                 (Justification.Etat.REFUSEE, 'Refuser')],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    commentaire_decision = forms.CharField(
        required=False, max_length=2000, label='Commentaire',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
