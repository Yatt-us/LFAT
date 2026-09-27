from django import forms
from decimal import Decimal
from django.db.models import Sum
from django.core.exceptions import ValidationError
from .models import (
    EcoleSettings, EmploiDuTemps, Etudiant, Classe, AnneeScolaire, Enseignant, Matiere, Note, Paiement,
    Presence, DossierInscriptionImage, CertificatFrequentation, ProgrammeMatiere, Inscription, CreanceScolaire, ModeleDocument
)
from django.utils import timezone
from .access import is_teacher_account

from django.db.models import ObjectDoesNotExist # Importation utile pour la gestion d'erreurs

# ====================================================================
# Fonctions utilitaires
# ====================================================================

def get_active_annee_scolaire():
    """Tente de récupérer l'année scolaire active."""
    try:
        return AnneeScolaire.objects.get(active=True)
    except ObjectDoesNotExist:
        return None

# ====================================================================
# FORMULAIRES PRINCIPAUX
# ====================================================================

# Formulaire pour l'élève
class EtudiantForm(forms.ModelForm):
    class Meta:
        model = Etudiant
        fields = [
            'nom', 'prenom', 'date_naissance', 'lieu_naissance', 'genre',
            'nationalite', 'adresse', 'ville', 'contact_parent', 'email_parent',
            'numero_matricule', 'classe', 'annee_scolaire_inscription',
            'photo_profil', 'statut'
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
            'date_naissance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'lieu_naissance': forms.TextInput(attrs={'class': 'form-control'}),
            'genre': forms.Select(attrs={'class': 'form-select'}),
            'nationalite': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse': forms.TextInput(attrs={'class': 'form-control'}),
            'ville': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_parent': forms.TextInput(attrs={'class': 'form-control'}),
            'email_parent': forms.EmailInput(attrs={'class': 'form-control'}),
            'numero_matricule': forms.TextInput(attrs={'class': 'form-control'}),
            'classe': forms.Select(attrs={'class': 'form-select'}),
            'annee_scolaire_inscription': forms.Select(attrs={'class': 'form-select'}),
            'photo_profil': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        super().__init__(*args, **kwargs)
        if not self.ecole:
            raise ValueError("Une école doit être fournie pour filtrer les classes et années scolaires.")

        annee_active = AnneeScolaire.objects.filter(active=True, ecole=self.ecole).first()
        classes = Classe.objects.filter(ecole=self.ecole)
        if annee_active:
            classes = classes.filter(annee_scolaire=annee_active)
        if self.instance.pk and self.instance.classe_id:
            classes = (classes | Classe.objects.filter(pk=self.instance.classe_id, ecole=self.ecole)).distinct()
        self.fields['classe'].queryset = classes.order_by('nom_classe')
        if not self.instance.pk and annee_active:
            self.fields['annee_scolaire_inscription'].initial = annee_active
        self.fields['annee_scolaire_inscription'].queryset = AnneeScolaire.objects.filter(
            ecole=self.ecole
        ).order_by('-annee')
        if self.instance.pk:
            self.fields['annee_scolaire_inscription'].disabled = True
            self.fields['classe'].disabled = True


class InscriptionForm(forms.ModelForm):
    class Meta:
        model = Inscription
        fields = ['classe', 'statut']
        widgets = {
            'classe': forms.Select(attrs={'class': 'form-select'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        self.annee_scolaire = kwargs.pop('annee_scolaire', None)
        super().__init__(*args, **kwargs)
        if self.ecole and self.annee_scolaire:
            self.fields['classe'].queryset = Classe.objects.filter(
                ecole=self.ecole, annee_scolaire=self.annee_scolaire
            ).order_by('nom_classe')
        else:
            self.fields['classe'].queryset = Classe.objects.none()


# Formulaire pour les images du dossier d'inscription
class DossierInscriptionImageForm(forms.ModelForm):
    class Meta:
        model = DossierInscriptionImage
        fields = ['image', 'description']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

# Formulaire pour les Notes
class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['matiere', 'valeur', 'periode_evaluation', 'type_evaluation', 'date_evaluation', 'annee_scolaire']
        widgets = {
            'matiere': forms.Select(attrs={'class': 'form-select'}),
            'periode_evaluation': forms.Select(attrs={'class': 'form-select'}),
            'type_evaluation': forms.TextInput(attrs={'class': 'form-control'}),
            'valeur': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '20'}),
            'date_evaluation': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'annee_scolaire': forms.HiddenInput(),
        }

    def clean_valeur(self):
        value = self.cleaned_data['valeur']
        if value < 0 or value > 20:
            raise ValidationError('La note doit être comprise entre 0 et 20.')
        return value

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.ecole = kwargs.pop('ecole', None) or getattr(getattr(user, 'profile', None), 'ecole', None)
        annee = kwargs.pop('annee_scolaire', None)
        self.classe = kwargs.pop('classe', None)
        super().__init__(*args, **kwargs)
        self.fields['periode_evaluation'].choices = [
            (value, label) for value, label in Note.PERIODE_EVALUATION_CHOICES
            if value != 'Annuelle'
        ]
        if not self.ecole:
            self.fields['matiere'].queryset = Matiere.objects.none()
            self.fields['annee_scolaire'].queryset = AnneeScolaire.objects.none()
            return
        programmes = ProgrammeMatiere.objects.filter(ecole=self.ecole, classe=self.classe) if self.classe else ProgrammeMatiere.objects.none()
        if user and is_teacher_account(user):
            programmes = programmes.filter(enseignant__user=user)
        matieres = Matiere.objects.filter(ecole=self.ecole, pk__in=programmes.values('matiere_id'))
        self.fields['matiere'].queryset = matieres.order_by('nom')
        annee = annee or AnneeScolaire.objects.filter(ecole=self.ecole, active=True).first()
        self.fields['annee_scolaire'].queryset = (
            AnneeScolaire.objects.filter(pk=annee.pk, ecole=self.ecole) if annee
            else AnneeScolaire.objects.none()
        )
        if annee:
            self.fields['annee_scolaire'].initial = annee.pk


class CreanceScolaireForm(forms.ModelForm):
    montant_confirme = forms.BooleanField(
        required=False,
        label="J'ai vérifié le montant historique",
    )

    class Meta:
        model = CreanceScolaire
        fields = ['motif', 'libelle', 'montant_du']
        widgets = {
            'motif': forms.Select(attrs={'class': 'form-select'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control'}),
            'montant_du': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.paiements.exists():
            self.fields['motif'].disabled = True
        if not self.instance.pk or not self.instance.a_verifier:
            self.fields.pop('montant_confirme')

    def clean(self):
        cleaned = super().clean()
        montant = cleaned.get('montant_du')
        if self.instance.pk and montant is not None:
            encaisse = self.instance.paiements.filter(annule=False).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
            if montant < encaisse and not self.instance.a_verifier:
                self.add_error('montant_du', "Ce montant est inférieur aux encaissements enregistrés.")
        return cleaned


class PaiementForm(forms.ModelForm):
    class Meta:
        model = Paiement
        fields = ['creance', 'montant', 'date_paiement', 'mode_paiement', 'recu_numero']
        widgets = {
            'creance': forms.Select(attrs={'class': 'form-select'}),
            'montant': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01'}),
            'date_paiement': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'mode_paiement': forms.Select(attrs={'class': 'form-select'}),
            'recu_numero': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        self.etudiant = kwargs.pop('etudiant', None)
        self.annee_scolaire = kwargs.pop('annee_scolaire', None)
        super().__init__(*args, **kwargs)
        if not self.ecole:
            raise ValueError("Une école doit être fournie pour le formulaire de paiement.")
        self.etudiant = self.etudiant or (self.instance.etudiant if self.instance.pk else None)
        self.annee_scolaire = self.annee_scolaire or (self.instance.annee_scolaire if self.instance.pk else None)
        if not self.etudiant or not self.annee_scolaire:
            raise ValueError("Un élève et une année scolaire sont nécessaires.")
        self.fields['creance'].required = True
        self.fields['creance'].queryset = CreanceScolaire.objects.filter(
            ecole=self.ecole, etudiant=self.etudiant, annee_scolaire=self.annee_scolaire,
        ).order_by('motif', 'libelle', 'pk')
        if self.instance.pk:
            self.fields['creance'].disabled = True

    def clean(self):
        cleaned = super().clean()
        creance = cleaned.get('creance')
        montant = cleaned.get('montant')
        if not creance or montant is None:
            return cleaned
        if (creance.ecole_id != self.ecole.pk or
                creance.etudiant_id != self.etudiant.pk or
                creance.annee_scolaire_id != self.annee_scolaire.pk):
            raise ValidationError("Ce frais ne concerne pas cet élève et cette année.")
        if creance.a_verifier:
            self.add_error('creance', "Vérifiez d'abord le montant de ce frais historique.")
        deja_paye = creance.paiements.filter(annule=False).exclude(pk=self.instance.pk).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
        if montant + deja_paye > creance.montant_du:
            self.add_error('montant', "Le paiement dépasse le solde restant de ce frais.")
        self.instance.ecole = self.ecole
        self.instance.etudiant = self.etudiant
        self.instance.annee_scolaire = self.annee_scolaire
        self.instance.motif_paiement = creance.motif
        if not self.instance.pk:
            self.instance.montant_du = None
            self.instance.statut = 'Payé'
        return cleaned

class PresenceForm(forms.ModelForm):
    statut_saisie = forms.ChoiceField(
        choices=[('', 'Non renseigné')] + Presence.STATUT_PRESENCE_CHOICES,
        required=False, label="Pointage", widget=forms.Select(attrs={'class': 'form-select presence-status'})
    )
    etudiant = forms.ModelChoiceField(queryset=Etudiant.objects.none(), widget=forms.HiddenInput())

    class Meta:
        model = Presence
        fields = [
            'statut_saisie', 'matiere', 'heure_debut_cours', 'heure_fin_cours',
            'motif_absence_retard', 'justificatif_fourni', 'etudiant',
        ]
        widgets = {
            'heure_debut_cours': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'heure_fin_cours': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'motif_absence_retard': forms.TextInput(attrs={'class': 'form-control'}),
            'justificatif_fourni': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'matiere': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        self.classe_obj = kwargs.pop('classe', None)
        self.annee_obj = kwargs.pop('annee_scolaire', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['etudiant'].label = ''
        if not self.ecole or not self.classe_obj or not self.annee_obj:
            for name in ('etudiant', 'matiere'):
                self.fields[name].queryset = self.fields[name].queryset.none()
            return
        self.fields['etudiant'].queryset = Etudiant.objects.filter(
            ecole=self.ecole, inscriptions__classe=self.classe_obj,
            inscriptions__annee_scolaire=self.annee_obj, inscriptions__statut='active'
        )
        programmes = ProgrammeMatiere.objects.filter(ecole=self.ecole, classe=self.classe_obj)
        if self.user and is_teacher_account(self.user):
            programmes = programmes.filter(enseignant=getattr(self.user, 'enseignant', None))
        self.fields['matiere'].queryset = Matiere.objects.filter(
            ecole=self.ecole, pk__in=programmes.values('matiere_id')
        )

    def clean(self):
        cleaned = super().clean()
        statut = cleaned.get('statut_saisie')
        if not statut and any(cleaned.get(field) for field in (
            'matiere', 'heure_debut_cours', 'heure_fin_cours',
            'motif_absence_retard', 'justificatif_fourni',
        )):
            self.add_error('statut_saisie', 'Choisissez un statut pour enregistrer ces détails.')
        debut = cleaned.get('heure_debut_cours')
        fin = cleaned.get('heure_fin_cours')
        if statut and statut != 'Présent' and bool(debut) != bool(fin):
            self.add_error('heure_fin_cours', 'Renseignez les deux heures ou laissez-les vides.')
        elif debut and fin and debut >= fin:
            self.add_error('heure_fin_cours', "L'heure de fin doit suivre l'heure de début.")
        return cleaned


# Formulaire pour les Enseignants
class EnseignantForm(forms.ModelForm):
    class Meta:
        model = Enseignant
        fields = ['nom', 'prenom', 'contact', 'email', 'specialite']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'prenom': forms.TextInput(attrs={'class': 'form-control'}),
            'contact': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'specialite': forms.TextInput(attrs={'class': 'form-control'}),
        }

# Formulaire pour les Matières
class MatiereForm(forms.ModelForm):
    class Meta:
        model = Matiere
        fields = ['nom', 'code_matiere']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control'}),
            'code_matiere': forms.TextInput(attrs={'class': 'form-control'}),
        }

# Formulaire pour les Classes


class ClasseForm(forms.ModelForm):
    class Meta:
        model = Classe
        fields = ['nom_classe', 'niveau', 'serie', 'enseignant_principal', 'annee_scolaire']
        widgets = {
            'nom_classe': forms.TextInput(attrs={'class': 'form-control'}),
            'niveau': forms.Select(attrs={'class': 'form-select'}),
            'serie': forms.TextInput(attrs={'class': 'form-control'}),
            'enseignant_principal': forms.Select(attrs={'class': 'form-select'}),
            'annee_scolaire': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        # On peut passer l'école depuis la vue
        self.ecole = kwargs.pop('ecole', None)
        super().__init__(*args, **kwargs)

        # Filtrage des enseignants par école si fourni
        if self.ecole:
            self.fields['enseignant_principal'].queryset = Enseignant.objects.filter(ecole=self.ecole)
        else:
            self.fields['enseignant_principal'].queryset = Enseignant.objects.none()

        # Récupération de l'année scolaire active
        annee_active = None
        if self.ecole:
            # ⚠️ filter(...).first() pour éviter MultipleObjectsReturned
            annee_active = AnneeScolaire.objects.filter(ecole=self.ecole, active=True).first()

        if annee_active and not self.instance.pk:
            # Pré-remplissage de l'année active par défaut pour la création
            self.fields['annee_scolaire'].initial = annee_active

        # Filtrer les années scolaires disponibles par école
        if self.ecole:
            self.fields['annee_scolaire'].queryset = AnneeScolaire.objects.filter(ecole=self.ecole).order_by('-annee')
        else:
            self.fields['annee_scolaire'].queryset = AnneeScolaire.objects.none()

        # Désactiver le champ année_scolaire si on modifie une classe existante
        if self.instance.pk:
            self.fields['annee_scolaire'].disabled = True


# Formulaire pour ProgrammeMatiere (lier matière à classe avec coefficient)
class ProgrammeMatiereForm(forms.ModelForm):
    class Meta:
        model = ProgrammeMatiere
        fields = ['classe', 'matiere', 'enseignant', 'coefficient']
        widgets = {
            'classe': forms.Select(attrs={'class': 'form-select'}),
            'matiere': forms.Select(attrs={'class': 'form-select'}),
            'enseignant': forms.Select(attrs={'class': 'form-select'}),
            'coefficient': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        super().__init__(*args, **kwargs)
        if not self.ecole:
            for name in ('classe', 'matiere', 'enseignant'):
                self.fields[name].queryset = self.fields[name].queryset.none()
            return
        self.fields['classe'].queryset = Classe.objects.filter(
            ecole=self.ecole, annee_scolaire__active=True, annee_scolaire__ecole=self.ecole
        )
        self.fields['matiere'].queryset = Matiere.objects.filter(ecole=self.ecole)
        self.fields['enseignant'].queryset = Enseignant.objects.filter(ecole=self.ecole)




class AnneeScolaireForm(forms.ModelForm):
    class Meta:
        model = AnneeScolaire
        fields = ['annee', 'date_debut', 'date_fin', 'active']
        widgets = {
            'annee': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 2023-2024'
            }),
            'date_debut': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'date_fin': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'annee': 'Année Scolaire',
            'active': 'Année Active (en cours)',
        }

    def __init__(self, *args, **kwargs):
        # Récupérer l'école depuis la vue
        self.ecole = kwargs.pop('ecole', None)
        super().__init__(*args, **kwargs)

        # Pré-remplissage automatique à la création
        if not self.instance.pk:
            today = timezone.localdate()
            start_year = today.year if today.month >= 8 else today.year - 1
            end_year = start_year + 1
            self.fields['annee'].initial = f"{start_year}-{end_year}"

        # Désactiver l'édition du champ année lors de la modification
        if self.instance.pk:
            self.fields['annee'].disabled = True

    def clean_annee(self):
        """Vérifie que l'année scolaire est unique pour l'école"""
        annee = self.cleaned_data['annee']
        ecole = self.ecole or getattr(self.instance, 'ecole', None)

        if ecole:
            qs = AnneeScolaire.objects.filter(annee=annee, ecole=ecole)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)  # Exclure l'instance actuelle
            if qs.exists():
                raise forms.ValidationError(
                    "Cette année scolaire existe déjà pour votre école."
                )
        return annee

    def clean(self):
        cleaned_data = super().clean()
        debut = cleaned_data.get('date_debut')
        fin = cleaned_data.get('date_fin')
        if debut and fin and fin <= debut:
            self.add_error('date_fin', 'La fin de l’année doit être postérieure à son début.')
        return cleaned_data



class CertificatFrequentationForm(forms.ModelForm):
    """Only the metadata which influences the issued school certificate."""

    class Meta:
        model = CertificatFrequentation
        fields = ['etudiant', 'date_delivrance', 'lieu_delivrance', 'mention_legale', 'remarque']
        widgets = {
            'etudiant': forms.Select(attrs={'class': 'form-select'}),
            'date_delivrance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'lieu_delivrance': forms.TextInput(attrs={'class': 'form-control'}),
            'mention_legale': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'remarque': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        ecole = kwargs.pop('ecole', None)
        super().__init__(*args, **kwargs)
        if ecole is None and user and user.is_authenticated:
            ecole = getattr(getattr(user, 'profile', None), 'ecole', None)
        annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first() if ecole else None
        if annee_active:
            self.fields['etudiant'].queryset = Etudiant.objects.filter(
                ecole=ecole, inscriptions__ecole=ecole,
                inscriptions__annee_scolaire=annee_active,
                inscriptions__statut='active', inscriptions__classe__isnull=False,
            ).distinct().order_by('nom', 'prenom')
        else:
            self.fields['etudiant'].queryset = Etudiant.objects.none()
        self.fields['date_delivrance'].initial = self.initial.get('date_delivrance', timezone.localdate())
        self.fields['mention_legale'].help_text = (
            "Facultatif : remplace la mention du modèle de votre école pour ce certificat."
        )


class EmploiDuTempsForm(forms.ModelForm):
    class Meta:
        model = EmploiDuTemps
        fields = ['classe', 'matiere', 'enseignant', 'jour', 'heure_debut', 'heure_fin']
        widgets = {
            'classe': forms.Select(attrs={'class': 'form-select'}),
            'matiere': forms.Select(attrs={'class': 'form-select'}),
            'enseignant': forms.Select(attrs={'class': 'form-select'}),
            'jour': forms.Select(attrs={'class': 'form-select'}),
            'heure_debut': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'heure_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.ecole = kwargs.pop('ecole', None)
        self.annee_scolaire = kwargs.pop('annee_scolaire', None)
        self.fixed_classe = kwargs.pop('fixed_classe', None)
        super().__init__(*args, **kwargs)
        if self.ecole is None:
            for field in ('classe', 'matiere', 'enseignant'):
                self.fields[field].queryset = self.fields[field].queryset.none()
            return
        if self.annee_scolaire is None:
            self.annee_scolaire = AnneeScolaire.objects.filter(ecole=self.ecole, active=True).first()
        classes = Classe.objects.filter(ecole=self.ecole)
        if self.annee_scolaire is not None:
            classes = classes.filter(annee_scolaire=self.annee_scolaire)
        else:
            classes = classes.none()
        self.fields['classe'].queryset = classes
        self.fields['matiere'].queryset = Matiere.objects.filter(ecole=self.ecole)
        self.fields['enseignant'].queryset = Enseignant.objects.filter(ecole=self.ecole)
        if self.fixed_classe is not None:
            self.fields['classe'].queryset = classes.filter(pk=self.fixed_classe.pk)
            self.fields['classe'].initial = self.fixed_classe
            self.fields['classe'].disabled = True

    def clean(self):
        cleaned = super().clean()
        classe = cleaned.get('classe')
        matiere = cleaned.get('matiere')
        enseignant = cleaned.get('enseignant')
        jour = cleaned.get('jour')
        debut = cleaned.get('heure_debut')
        fin = cleaned.get('heure_fin')
        if classe and self.annee_scolaire and classe.annee_scolaire_id != self.annee_scolaire.pk:
            self.add_error('classe', 'La classe doit appartenir à l’année scolaire sélectionnée.')
        if not self.ecole or not self.annee_scolaire or not classe:
            return cleaned
        if classe.ecole_id != self.ecole.pk or self.annee_scolaire.ecole_id != self.ecole.pk:
            self.add_error('classe', "La classe et l'année doivent appartenir à votre école.")
            return cleaned
        if matiere and enseignant:
            programme = ProgrammeMatiere.objects.filter(
                ecole=self.ecole, classe=classe, matiere=matiere,
            ).first()
            if programme is None:
                self.add_error('matiere', 'Ajoutez cette matière au programme de la classe avant de la planifier.')
            elif programme.enseignant_id != enseignant.pk:
                self.add_error('enseignant', "Affectez cet enseignant à la matière dans le programme de la classe.")
        if not (jour and debut and fin) or debut >= fin:
            return cleaned
        autres_blocs = EmploiDuTemps.objects.filter(
            ecole=self.ecole, annee_scolaire=self.annee_scolaire,
            jour=jour, heure_debut__lt=fin, heure_fin__gt=debut,
        ).exclude(pk=self.instance.pk)
        if autres_blocs.filter(classe=classe).exists():
            self.add_error('heure_debut', 'Un autre cours de cette classe chevauche cette plage horaire.')
        if enseignant and autres_blocs.filter(enseignant=enseignant).exists():
            self.add_error('enseignant', 'Cet enseignant donne déjà un cours sur cette plage horaire.')
        return cleaned


class EcoleSettingsForm(forms.ModelForm):
    """
    Formulaire de gestion complète des paramètres d'établissement.
    Compatible avec les vues Admin et personnalisées.
    """
    class Meta:
        model = EcoleSettings
        fields = [
            'ministere',
            'academie',
            'commune',
            'nom_etablissement',
            'adresse_etablissement',
            'telephone',
            'email_contact',
            'site_web',
            'code_etablissement',
            'logo',
            'cachet_admin',
            'signature_directeur',
            'titre_signataire',
            'nom_signataire',
        ]

        # Définition des widgets uniformes
        widgets = {
            'ministere': forms.TextInput(attrs={'class': 'form-control'}),
            'academie': forms.TextInput(attrs={'class': 'form-control'}),
            'commune': forms.TextInput(attrs={'class': 'form-control'}),
            'nom_etablissement': forms.TextInput(attrs={'class': 'form-control'}),
            'adresse_etablissement': forms.TextInput(attrs={'class': 'form-control'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'email_contact': forms.EmailInput(attrs={'class': 'form-control'}),
            'site_web': forms.URLInput(attrs={'class': 'form-control'}),
            'code_etablissement': forms.TextInput(attrs={'class': 'form-control'}),
            'titre_signataire': forms.TextInput(attrs={'class': 'form-control'}),
            'nom_signataire': forms.TextInput(attrs={'class': 'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'cachet_admin': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'signature_directeur': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        """Valide les tailles des fichiers institutionnels."""
        cleaned_data = super().clean()

        # Vérifie la taille maximale des fichiers image
        max_size = 3 * 1024 * 1024  # 3 Mo
        for champ in ['logo', 'cachet_admin', 'signature_directeur']:
            fichier = cleaned_data.get(champ)
            if fichier and hasattr(fichier, 'size') and fichier.size > max_size:
                raise ValidationError(
                    f"Le fichier '{champ}' dépasse la taille maximale autorisée (3 Mo)."
                )

        return cleaned_data


# Une configuration enregistrée par école et par type de document.


class ModeleDocumentForm(forms.ModelForm):
    class Meta:
        model = ModeleDocument
        fields = [
            'titre', 'entete', 'corps', 'pied_de_page', 'mention',
            'titre_signataire', 'afficher_logo', 'afficher_cachet',
            'afficher_signature', 'actif',
        ]
        labels = {
            'titre': 'Titre du document',
            'entete': 'En-tête',
            'corps': 'Texte principal',
            'pied_de_page': 'Pied de page',
            'mention': 'Mention complémentaire',
            'titre_signataire': 'Qualité du signataire',
            'afficher_logo': 'Afficher le logo',
            'afficher_cachet': 'Afficher le cachet',
            'afficher_signature': 'Afficher la signature',
            'actif': 'Modèle disponible pour les élèves',
        }
        widgets = {
            'titre': forms.TextInput(attrs={'class': 'form-control'}),
            'entete': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'corps': forms.Textarea(attrs={'class': 'form-control', 'rows': 8}),
            'pied_de_page': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'mention': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'titre_signataire': forms.TextInput(attrs={'class': 'form-control'}),
            'afficher_logo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'afficher_cachet': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'afficher_signature': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'actif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'entete': "Texte placé au-dessus du titre, par exemple l'académie et l'établissement.",
            'corps': "Utilisez les variables indiquées ci-dessous pour les informations de l'élève.",
            'pied_de_page': "Coordonnées ou informations institutionnelles.",
            'mention': "Texte facultatif affiché après le corps du document.",
            'titre_signataire': "Exemple : Le directeur ou La directrice.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.type_document != ModeleDocument.TYPE_AUTRE:
            self.fields.pop('actif')
