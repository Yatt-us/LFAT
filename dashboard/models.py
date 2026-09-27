from datetime import timedelta
from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
from .private_media import private_media_storage
from django.utils import timezone # Pour les dates/heures actuelles




# ====================================================================
# PARAMÈTRES ET GESTION INSTITUTIONNELLE
# ====================================================================

# Modèle pour les paramètres généraux de l'école (incluant les assets pour les documents : Logo, Cachet, Signature)

from django.db import models




class EcoleSettings(models.Model):
    """
    Configuration d'une école (multi-instances autorisées)
    """
    # ⚠️ Suppression du champ unique_instance et du clean() restrictif
    # Chaque école aura désormais sa propre configuration

    # Informations institutionnelles
    ministere = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Ministère de Tutelle",
        help_text="Exemple : Ministère de l’Éducation Nationale"
    )
    academie = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Académie / Inspection",
        help_text="Exemple : Académie de Bamako Rive Droite"
    )
    commune = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Commune",
        help_text="Exemple : Commune IV du District de Bamako"
    )

    # Informations de l’établissement
    nom_etablissement = models.CharField(
        max_length=255,
        verbose_name="Nom de l'Établissement"
    )
    adresse_etablissement = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Adresse"
    )
    telephone = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Téléphone de l'Établissement"
    )
    email_contact = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email de Contact"
    )
    site_web = models.URLField(
        blank=True,
        null=True,
        verbose_name="Site Web"
    )

    # Identifiants administratifs
    code_etablissement = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,  # ✅ Chaque école doit avoir un code unique
        verbose_name="Code de l'Établissement",
        help_text="Code attribué par le ministère ou la direction académique"
    )

    # Éléments graphiques pour les documents officiels
    logo = models.ImageField(
        upload_to='ecoles/logos/',
        blank=True,
        null=True,
        verbose_name="Logo de l'École"
    )
    cachet_admin = models.ImageField(
        upload_to='settings/assets/',
        storage=private_media_storage,
        blank=True,
        null=True,
        verbose_name="Cachet (Sceau) de l'Administration"
    )
    signature_directeur = models.ImageField(
        upload_to='settings/assets/',
        storage=private_media_storage,
        blank=True,
        null=True,
        verbose_name="Signature du Directeur/Responsable"
    )

    titre_signataire = models.CharField(
        max_length=100,
        default='Le Directeur',
        verbose_name="Titre du Signataire"
    )
    nom_signataire = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Nom du Signataire",
        help_text="Nom du directeur ou responsable signataire"
    )

    date_mise_a_jour = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière mise à jour"
    )

    class Meta:
        verbose_name = "École"
        verbose_name_plural = "Écoles"
        ordering = ['nom_etablissement']

     # ⚡ Période d'essai gratuite et activation
    date_fin_essai = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Fin de la période d'essai gratuite"
    )
    STATUT_ABONNEMENT_CHOICES = [
        ('trial', 'Essai'), ('active', 'Actif'), ('expired', 'Expiré'), ('suspended', 'Suspendu'),
    ]
    statut_abonnement = models.CharField(max_length=20, choices=STATUT_ABONNEMENT_CHOICES, default='trial')
    date_fin_abonnement = models.DateTimeField(blank=True, null=True)
    est_active = models.BooleanField(
        default=True,
        verbose_name="École active",
        help_text="Indique si l'école peut utiliser le système"
    )

    def save(self, *args, **kwargs):
        # Si création, définir la fin de la période d'essai à 30 jours
        if not self.pk:
            self.date_fin_essai = timezone.now() + timedelta(days=30)
        super().save(*args, **kwargs)

    def periode_essai_expiree(self):
        """Retourne True si la période d'essai est terminée"""
        return self.date_fin_essai and timezone.now() > self.date_fin_essai

    # Optionnel : vérifier si l'école peut utiliser le système
    def peut_utiliser_systeme(self):
        if not self.est_active or self.statut_abonnement in {'expired', 'suspended'}:
            return False
        if self.statut_abonnement == 'active':
            return not self.date_fin_abonnement or timezone.now() <= self.date_fin_abonnement
        return bool(self.date_fin_essai and timezone.now() <= self.date_fin_essai)


    def __str__(self):
        return f"{self.nom_etablissement} ({self.code_etablissement or 'Sans code'})"
    


class Profile(models.Model):
    ROLE_CHOICES = [
        ('unassigned', 'À définir'), ('school_admin', 'Administrateur'),
        ('director', 'Direction'), ('secretary', 'Secrétariat'),
        ('accountant', 'Comptabilité'), ('teacher', 'Enseignant'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    ecole = models.ForeignKey("EcoleSettings", on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='unassigned')

    def __str__(self):
        return f"{self.user.username} "



class DemandeAbonnement(models.Model):
    STATUS_CHOICES = [('pending', 'En attente'), ('paid', 'Payé'), ('rejected', 'Rejeté')]
    ecole = models.ForeignKey(EcoleSettings, on_delete=models.PROTECT, related_name='demandes_abonnement')
    montant = models.DecimalField(max_digits=10, decimal_places=2, default=25000)
    mode_paiement = models.CharField(max_length=50, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    cree_le = models.DateTimeField(auto_now_add=True)
    confirme_le = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-cree_le']
        verbose_name = 'Demande d’abonnement'
        verbose_name_plural = 'Demandes d’abonnement'

    def __str__(self):
        return f"{self.ecole.nom_etablissement} — {self.montant} FCFA ({self.get_statut_display()})"


# Modèle pour l'année scolaire (très important pour filtrer les données)
from django.db import models
class AnneeScolaire(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École"
    )
    
    annee = models.CharField(
        max_length=9,
        verbose_name="Année Scolaire",
        help_text="Exemple : 2024-2025"
    )
    date_debut = models.DateField(verbose_name="Date de Début")
    date_fin = models.DateField(verbose_name="Date de Fin")
    active = models.BooleanField(
        default=False,
        verbose_name="Active (Année en cours)",
        help_text="Si cochée, cette année sera considérée comme l'année scolaire en cours."
    )

    class Meta:
        verbose_name = "Année Scolaire"
        verbose_name_plural = "Années Scolaires"
        ordering = ['-annee']  # Affiche l'année la plus récente en premier
        unique_together = ('ecole', 'annee')  # Unicité par école
        constraints = [models.UniqueConstraint(fields=['ecole'], condition=Q(active=True), name='uniq_annee_active_par_ecole')]

    def __str__(self):
        return f"{self.annee} ({self.ecole})"

    def clean(self):
        super().clean()
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            raise ValidationError({'date_fin': "La fin de l'année scolaire doit suivre son début."})

    def save(self, *args, **kwargs):
        # Garantit une seule année active, avec une contrainte complémentaire en base.
        with transaction.atomic():
            if self.active:
                AnneeScolaire.objects.filter(ecole_id=self.ecole_id, active=True).exclude(pk=self.pk).update(active=False)
            super().save(*args, **kwargs)




# ====================================================================
# PERSONNEL
# ====================================================================

# Modèle pour les enseignants
class Enseignant(models.Model):
    ecole = models.ForeignKey(
     'EcoleSettings',
     on_delete=models.CASCADE,
     verbose_name="École",
     related_name='enseignants')  # <-- ajoute ce related_name


    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Utilisateur Django")
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    contact = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact Téléphonique")
    email = models.EmailField(blank=True, null=True, verbose_name="Adresse Email")
    specialite = models.CharField(max_length=100, blank=True, null=True, verbose_name="Spécialité/Matière principale")

    class Meta:
        verbose_name = "Enseignant"
        verbose_name_plural = "Enseignants"
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.prenom} {self.nom}"


# ====================================================================
# STRUCTURE SCOLAIRE
# ====================================================================

# Modèle pour les classes (avec niveau et série si applicable)
class Classe(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École")
    
    nom_classe = models.CharField(max_length=100, verbose_name="Nom de la Classe") # Ex: "7ème Année A", "Terminale L"
    # Les codes historiques restent lisibles ; les libellés suivent l'organisation malienne.
    NIVEAU_CHOICES = [
        ('1AP', '1ère année fondamentale'), ('2AP', '2e année fondamentale'),
        ('3AP', '3e année fondamentale'), ('4AP', '4e année fondamentale'),
        ('5AP', '5e année fondamentale'), ('6AP', '6e année fondamentale'),
        ('7AP', '7e année fondamentale'), ('8AP', '8e année fondamentale'),
        ('9AP', '9e année fondamentale (DEF)'),
        ('1AS', '10e année commune'), ('2AS', '11e année'),
        ('TLE', '12e année / Terminale'),
        ('TL', 'Terminale L (ancien code)'),
        ('TS', 'Terminale S (ancien code)'),
        ('TC', 'Terminale C (ancien code)'),
    ]
    CYCLE_FONDAMENTAL_1 = 'fondamental_1'
    CYCLE_FONDAMENTAL_2 = 'fondamental_2'
    CYCLE_LYCEE = 'lycee'
    niveau = models.CharField(max_length=50, verbose_name="Niveau Scolaire", choices=NIVEAU_CHOICES)
    serie = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Série (pour le lycée)",
        help_text="Par exemple : Lettres, Sciences, SES, TLL, TAL, TSS, TSEco, TSExp ou TSE."
    )
    enseignant_principal = models.ForeignKey(Enseignant, on_delete=models.SET_NULL, null=True, blank=True,related_name='classes_principales', verbose_name= "Enseignant Principal")
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année Scolaire")

    class Meta:
        verbose_name = "Classe"
        verbose_name_plural = "Classes"
        unique_together = ('nom_classe', 'annee_scolaire')
        ordering = ['annee_scolaire', 'niveau', 'nom_classe']

    @property
    def cycle_scolaire(self):
        """Cycle malien déduit du niveau, sans deuxième champ à synchroniser."""
        if self.niveau in {'1AP', '2AP', '3AP', '4AP', '5AP', '6AP'}:
            return self.CYCLE_FONDAMENTAL_1
        if self.niveau in {'7AP', '8AP', '9AP'}:
            return self.CYCLE_FONDAMENTAL_2
        if self.niveau in {'1AS', '2AS', 'TLE', 'TL', 'TS', 'TC'}:
            return self.CYCLE_LYCEE
        return None

    def clean(self):
        super().clean()
        errors = {}
        if self.ecole_id and self.annee_scolaire_id and self.annee_scolaire.ecole_id != self.ecole_id:
            errors['annee_scolaire'] = "L'année scolaire doit appartenir à l'école."
        if self.ecole_id and self.enseignant_principal_id and self.enseignant_principal.ecole_id != self.ecole_id:
            errors['enseignant_principal'] = "L'enseignant principal doit appartenir à l'école."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.nom_classe} ({self.annee_scolaire.annee})"

# Modèle pour les matières
class Matiere(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
        )
    
    nom = models.CharField(max_length=100, verbose_name="Nom de la Matière")
    code_matiere = models.CharField(max_length=10, blank=True, null=True, verbose_name="Code Matière")

    class Meta:
        verbose_name = "Matière"
        verbose_name_plural = "Matières"
        ordering = ['nom']
        constraints = [
            models.UniqueConstraint(fields=['ecole', 'nom'], name='uniq_matiere_nom_par_ecole'),
            models.UniqueConstraint(fields=['ecole', 'code_matiere'], condition=Q(code_matiere__isnull=False) & ~Q(code_matiere=''), name='uniq_matiere_code_par_ecole'),
        ]

    def __str__(self):
        return self.nom

# Modèle pour lier les matières aux classes avec leur coefficient
class ProgrammeMatiere(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, verbose_name="Classe")
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, verbose_name="Matière")
    enseignant = models.ForeignKey(Enseignant, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Enseignant de la matière")
    coefficient = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1)], verbose_name="Coefficient"
    )

    class Meta:
        verbose_name = "Programme Matière par Classe"
        verbose_name_plural = "Programmes Matières par Classe"
        unique_together = ('classe', 'matiere')
        ordering = ['classe', 'matiere__nom']
        constraints = [
            models.CheckConstraint(condition=Q(coefficient__gte=1), name='coeff_programme_positif'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.ecole_id and self.classe_id and self.classe.ecole_id != self.ecole_id:
            errors['classe'] = "La classe doit appartenir à l'école."
        if self.ecole_id and self.matiere_id and self.matiere.ecole_id != self.ecole_id:
            errors['matiere'] = "La matière doit appartenir à l'école."
        if self.ecole_id and self.enseignant_id and self.enseignant.ecole_id != self.ecole_id:
            errors['enseignant'] = "L'enseignant doit appartenir à l'école."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.matiere.nom} ({self.coefficient}) en {self.classe.nom_classe}"


# ====================================================================
# ÉTUDIANTS / ÉLÈVES ET INSCRIPTION
# ====================================================================

# Modèle pour les étudiants/élèves
class Etudiant(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    SITUATION_CHOICES = [('Actif', 'Actif'), ('Ancien', 'Ancien'), ('Suspendu', 'Suspendu'), ('Radié', 'Radié')]

    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom(s)")
    date_naissance = models.DateField(verbose_name="Date de Naissance")
    lieu_naissance = models.CharField(max_length=100, blank=True, null=True, verbose_name="Lieu de Naissance")
    genre = models.CharField(max_length=1, choices=SEXE_CHOICES, verbose_name="Sexe")
    nationalite = models.CharField(max_length=50, default='Malienne', verbose_name="Nationalité")
    adresse = models.CharField(max_length=200, blank=True, null=True, verbose_name="Adresse Résidentielle")
    ville = models.CharField(max_length=100, default='Bamako', verbose_name="Ville")
    contact_parent = models.CharField(max_length=50, blank=True, null=True, verbose_name="Contact Parent/Tuteur")
    email_parent = models.EmailField(blank=True, null=True, verbose_name="Email Parent/Tuteur")
    numero_matricule = models.CharField(max_length=50, blank=True, null=True, verbose_name="Numéro Matricule")
    
    classe = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Classe Actuelle")
    annee_scolaire_inscription = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année d'Inscription")
    date_inscription = models.DateField(default=timezone.now, verbose_name="Date d'Inscription")
    photo_profil = models.ImageField(upload_to='photos_profil_eleves/', storage=private_media_storage, blank=True, null=True, verbose_name="Photo de Profil")
    statut = models.CharField(max_length=20, choices=SITUATION_CHOICES, default='Actif', verbose_name="Statut Actuel")


    class Meta:
        verbose_name = "Élève"
        verbose_name_plural = "Élèves"
        ordering = ['classe__nom_classe', 'nom', 'prenom']
        constraints = [models.UniqueConstraint(
            fields=['ecole', 'numero_matricule'],
            condition=Q(numero_matricule__isnull=False) & ~Q(numero_matricule=''),
            name='uniq_matricule_par_ecole',
        )]

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.classe.nom_classe if self.classe else 'Non assigné'})"

    def get_tuteurs(self):
        return [lien.tuteur for lien in self.liens_tuteurs.select_related('tuteur')]

    def get_responsable_financier(self):
        lien = self.liens_tuteurs.filter(est_responsable_financier=True).select_related('tuteur').first()
        return lien.tuteur if lien else None

    def get_contact_urgence(self):
        lien = self.liens_tuteurs.filter(est_contact_urgence=True).select_related('tuteur').first()
        return lien.tuteur if lien else None

    def fratrie(self):
        """Retourne la liste des autres élèves de l'école partageant un tuteur ou ayant le même contact parent."""
        tuteurs_ids = self.liens_tuteurs.values_list('tuteur_id', flat=True)
        q = Q(liens_tuteurs__tuteur_id__in=tuteurs_ids)
        if self.contact_parent:
            q |= Q(contact_parent=self.contact_parent)
        return Etudiant.objects.filter(ecole_id=self.ecole_id).filter(q).exclude(pk=self.pk).distinct()


class Inscription(models.Model):
    STATUT_CHOICES = [('active', 'Active'), ('suspendue', 'Suspendue'), ('terminee', 'Terminée'), ('transferee', 'Transférée')]
    ecole = models.ForeignKey(EcoleSettings, on_delete=models.CASCADE, related_name='inscriptions')
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='inscriptions')
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.PROTECT, related_name='inscriptions')
    classe = models.ForeignKey(Classe, on_delete=models.PROTECT, related_name='inscriptions', null=True, blank=True)
    date_inscription = models.DateField(default=timezone.localdate)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='active')

    class Meta:
        unique_together = [('etudiant', 'annee_scolaire')]
        ordering = ['annee_scolaire__annee', 'classe__nom_classe', 'etudiant__nom']
        verbose_name = 'Inscription annuelle'
        verbose_name_plural = 'Inscriptions annuelles'

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if self.etudiant_id and self.ecole_id and self.etudiant.ecole_id != self.ecole_id:
            errors['etudiant'] = 'L’élève doit appartenir à la même école.'
        if self.annee_scolaire_id and self.ecole_id and self.annee_scolaire.ecole_id != self.ecole_id:
            errors['annee_scolaire'] = 'L’année doit appartenir à la même école.'
        if self.classe_id:
            if self.classe.ecole_id != self.ecole_id:
                errors['classe'] = 'La classe doit appartenir à la même école.'
            if self.annee_scolaire_id and self.classe.annee_scolaire_id != self.annee_scolaire_id:
                errors['classe'] = 'La classe doit appartenir à l’année sélectionnée.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.etudiant} — {self.annee_scolaire}"

# Modèle pour les photos des dossiers d'inscription
class DossierInscriptionImage(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='dossier_images', verbose_name="Élève")
    image = models.ImageField(upload_to='dossiers_inscription/', storage=private_media_storage, verbose_name="Fichier (Image ou PDF)")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Description du document")
    date_telechargement = models.DateTimeField(auto_now_add=True, verbose_name="Date de Téléchargement")

    class Meta:
        verbose_name = "Document d'Inscription"
        verbose_name_plural = "Documents d'Inscription"
        ordering = ['etudiant', 'description']

    def __str__(self):
        return f"Dossier de {self.etudiant} - {self.description or 'Document'}"


# ====================================================================
# NOTES ET ÉVALUATIONS
# ====================================================================

# Modèle pour les notes des élèves
class Note(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    
    PERIODE_EVALUATION_CHOICES = [
        ('Trimestre 1', 'Trimestre 1'), ('Trimestre 2', 'Trimestre 2'),
        ('Trimestre 3', 'Trimestre 3'), ('Annuelle', 'Annuelle'),
    ]

    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='notes')
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, verbose_name="Matière")
    valeur = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(20)], verbose_name="Note Obtenue (sur 20)")
    periode_evaluation = models.CharField(max_length=20, choices=PERIODE_EVALUATION_CHOICES, verbose_name="Période d'Évaluation")
    type_evaluation = models.CharField(max_length=50, blank=True, null=True, verbose_name="Type d'Évaluation")
    date_evaluation = models.DateField(default=timezone.now, verbose_name="Date de l'Évaluation")
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année Scolaire")

    class Meta:
        verbose_name = "Note"
        verbose_name_plural = "Notes"
        unique_together = ('etudiant', 'matiere', 'periode_evaluation', 'annee_scolaire')
        ordering = ['annee_scolaire', 'etudiant', 'periode_evaluation', 'matiere__nom']

    def __str__(self):
        return f"{self.etudiant.prenom} {self.etudiant.nom} - {self.matiere.nom} ({self.periode_evaluation}): {self.valeur}/20"

    def get_coefficient(self):
        """Retourne le coefficient explicite ou signale un programme incomplet."""
        try:
            inscription = Inscription.objects.get(
                etudiant=self.etudiant, annee_scolaire=self.annee_scolaire,
                ecole=self.ecole,
            )
            return ProgrammeMatiere.objects.get(
                classe=inscription.classe, matiere=self.matiere, ecole=self.ecole,
            ).coefficient
        except (Inscription.DoesNotExist, ProgrammeMatiere.DoesNotExist) as exc:
            raise ValidationError(
                'Aucun coefficient de programme explicite pour cette note.'
            ) from exc


# ====================================================================
# FINANCES ET PAIEMENTS
# ====================================================================

# Modèle pour le suivi des paiements
class Paiement(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    
    STATUT_PAIEMENT_CHOICES = [('Payé', 'Payé'), ('Impayé', 'Impayé'), ('Partiel', 'Partiel')]
    MOTIF_PAIEMENT_CHOICES = [
        ('Frais de Scolarité', 'Frais de Scolarité'), ('Frais d\'Inscription', 'Frais d\'Inscription'),
        ('Cotisation APEM', 'Cotisation APEM'), ('Tenue Scolaire', 'Tenue Scolaire'),
        ('Repas Scolaire', 'Repas Scolaire'), ('Autres', 'Autres'),
    ]
    MODE_PAIEMENT_CHOICES = [
        ('Espèces', 'Espèces'),
        ('Orange Money', 'Orange Money Mali'),
        ('Wave', 'Wave Mali'),
        ('Moov Money', 'Moov Africa Malitel'),
        ('Sama Money', 'Sama Money'),
        ('Chèque', 'Chèque'),
        ('Virement Bancaire', 'Virement Bancaire'),
        ('Mobile Money', 'Mobile Money'),
    ]

    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='paiements')
    creance = models.ForeignKey('CreanceScolaire', on_delete=models.PROTECT, related_name='paiements', null=True, blank=True, verbose_name="Frais concerné")
    montant = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant Payé (FCFA)")
    # Ancienne saisie conservée pour la traçabilité des données historiques.
    montant_du = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant dû historique", blank=True, null=True)
    date_paiement = models.DateField(default=timezone.now, verbose_name="Date du Paiement")
    motif_paiement = models.CharField(max_length=100, choices=MOTIF_PAIEMENT_CHOICES, verbose_name="Motif du Paiement")
    statut = models.CharField(max_length=20, choices=STATUT_PAIEMENT_CHOICES, default='Payé', verbose_name="Statut du Paiement")
    mode_paiement = models.CharField(max_length=50, choices=MODE_PAIEMENT_CHOICES, verbose_name="Mode de Paiement")
    reference_transaction = models.CharField(max_length=100, blank=True, null=True, verbose_name="Réf. Transaction / Chèque")
    telephone_payeur = models.CharField(max_length=30, blank=True, null=True, verbose_name="N° Tél. Payeur (Mobile Money)")
    recu_code_securise = models.CharField(max_length=64, blank=True, null=True, verbose_name="Code sécurisé de vérification")
    recu_numero = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Numéro de Reçu")
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année Scolaire Concernée")
    enregistre_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Enregistré par")
    annule = models.BooleanField(default=False, verbose_name="Paiement annulé")
    annule_le = models.DateTimeField(null=True, blank=True)
    annule_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='paiements_annules')

    def clean(self):
        super().clean()
        if self.montant is not None and self.montant <= 0 and not self.annule:
            raise ValidationError({'montant': "Un encaissement doit être supérieur à zéro."})
        if self.creance_id:
            if (self.ecole_id != self.creance.ecole_id or
                    self.etudiant_id != self.creance.etudiant_id or
                    self.annee_scolaire_id != self.creance.annee_scolaire_id or
                    self.motif_paiement != self.creance.motif):
                raise ValidationError("Le paiement et le frais doivent concerner la même école, le même élève, la même année et le même motif.")


    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ['-date_paiement', 'etudiant__nom']

    def __str__(self):
        return f"Encaissement de {self.etudiant.prenom} {self.etudiant.nom} - {self.montant} FCFA"




class CreanceScolaire(models.Model):
    """Montant demandé à un élève pour un frais donné; les paiements sont séparés."""

    ecole = models.ForeignKey('EcoleSettings', on_delete=models.CASCADE, related_name='creances')
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='creances')
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, related_name='creances')
    motif = models.CharField(max_length=100, choices=Paiement.MOTIF_PAIEMENT_CHOICES)
    libelle = models.CharField(max_length=200, blank=True)
    montant_du = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    date_echeance = models.DateField(blank=True, null=True, verbose_name="Date limite d'exigibilité")
    remise_type = models.CharField(
        max_length=30,
        choices=[
            ('aucune', 'Aucune'),
            ('fratrie', 'Remise fratrie'),
            ('bourse', 'Bourse d’étude / Cas social'),
            ('personnel', 'Enfant du personnel'),
            ('autre', 'Autre remise exceptionnelle'),
        ],
        default='aucune',
        verbose_name="Type de remise",
    )
    remise_montant = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Montant de remise (FCFA)",
    )
    origine_historique = models.BooleanField(default=False)
    a_verifier = models.BooleanField(default=False, verbose_name="Montant historique à vérifier")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Frais scolaire dû"
        verbose_name_plural = "Frais scolaires dus"
        ordering = ['etudiant__nom', 'motif', 'pk']

    def clean(self):
        super().clean()
        if self.etudiant_id and self.ecole_id and self.etudiant.ecole_id != self.ecole_id:
            raise ValidationError({'etudiant': "L'élève doit appartenir à l'école."})
        if self.annee_scolaire_id and self.ecole_id and self.annee_scolaire.ecole_id != self.ecole_id:
            raise ValidationError({'annee_scolaire': "L'année scolaire doit appartenir à l'école."})

    @property
    def montant_brut(self):
        return self.montant_du

    @montant_brut.setter
    def montant_brut(self, value):
        self.montant_du = value

    @property
    def montant_net(self):
        return max(Decimal('0.00'), self.montant_du - (self.remise_montant or Decimal('0.00')))

    @property
    def solde_restant(self):
        return max(Decimal('0.00'), self.montant_net - self.montant_paye)

    @property
    def est_soldee(self):
        return self.solde_restant <= Decimal('0.00')

    @property
    def est_en_retard(self):
        if not self.date_echeance:
            return False
        return not self.est_soldee and self.date_echeance < timezone.localdate()

    @property
    def montant_paye(self):
        if hasattr(self, 'total_paye_calcule'):
            return self.total_paye_calcule or Decimal('0.00')
        return self.paiements.filter(annule=False).aggregate(total=models.Sum('montant'))['total'] or Decimal('0.00')

    @property
    def solde_restant(self):
        return max(self.montant_du - self.montant_paye, Decimal('0.00'))

    @property
    def trop_percu(self):
        return max(self.montant_paye - self.montant_du, Decimal('0.00'))

    @property
    def statut(self):
        if self.a_verifier:
            return 'À vérifier'
        if self.solde_restant == 0:
            return 'Payé'
        if self.montant_paye:
            return 'Partiel'
        return 'Impayé'

    def __str__(self):
        return f"{self.etudiant} - {self.motif} : {self.montant_du} FCFA"


# ====================================================================
# ABSENCES ET PRÉSENCES
# ====================================================================

# Modèle pour le suivi des présences
class Presence(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    STATUT_PRESENCE_CHOICES = [
        ('Présent', 'Présent'), ('Absent', 'Absent'),
        ('Retard', 'Retard'), ('Excusé', 'Excusé'),
    ]

    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='presences')
    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, verbose_name="Classe concernée")
    date = models.DateField(verbose_name="Date de la Présence")
    statut = models.CharField(max_length=20, choices=STATUT_PRESENCE_CHOICES, verbose_name="Statut")
    matiere = models.ForeignKey(Matiere, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Matière (optionnel)")
    heure_debut_cours = models.TimeField(blank=True, null=True, verbose_name="Heure de Début du Cours")
    heure_fin_cours = models.TimeField(blank=True, null=True, verbose_name="Heure de Fin du Cours")
    motif_absence_retard = models.TextField(blank=True, null=True, verbose_name="Motif (si absent/retard)")
    justificatif_fourni = models.BooleanField(default=False, verbose_name="Justificatif Fourni ?")
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année Scolaire")
    enregistre_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Enregistré par")


    class Meta:
        verbose_name = "Présence"
        verbose_name_plural = "Présences"
        constraints = [models.UniqueConstraint(
            fields=['etudiant', 'classe', 'date', 'annee_scolaire'],
            name='uniq_presence_par_classe_et_jour',
        )]
        ordering = ['-date', 'classe__nom_classe', 'etudiant__nom']

    def __str__(self):
        return f"{self.etudiant.prenom} {self.etudiant.nom} - {self.date} ({self.statut})"


# ====================================================================
# DOCUMENTS OFFICIELS
# ====================================================================

# Modèle pour les certificats de fréquentation (pour garder une trace des certificats générés)
# Les assets (logo, cachet, signature) sont récupérés via le modèle EcoleSettings lors de la génération.

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

class CertificatFrequentation(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École"
    )
    etudiant = models.ForeignKey("dashboard.Etudiant", on_delete=models.CASCADE, verbose_name="Élève")
    annee_scolaire = models.ForeignKey("dashboard.AnneeScolaire", on_delete=models.CASCADE, verbose_name="Année Scolaire")
    date_delivrance = models.DateField(default=timezone.now, verbose_name="Date de Délivrance")
    numero_certificat = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name="Numéro du Certificat")
    lieu_delivrance = models.CharField(max_length=100, verbose_name="Lieu de délivrance", blank=True, null=True, default="")

    fichier_pdf = models.FileField(upload_to='certificats_frequentation/', storage=private_media_storage, blank=True, null=True, verbose_name="Fichier PDF du Certificat")
    delivre_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Délivré par")

    cachet_utilise = models.FileField(upload_to='certificats/assets/', storage=private_media_storage, blank=True, null=True, verbose_name="Cachet (Sceau) utilisé")
    signature_utilisee = models.FileField(upload_to='certificats/assets/', storage=private_media_storage, blank=True, null=True, verbose_name="Signature utilisée")

    ministere = models.CharField(max_length=255, blank=True, default='', verbose_name="Ministère de tutelle")
    academie = models.CharField(max_length=255, blank=True, default='', verbose_name="Académie / CAP")
    etablissement_reference = models.CharField(max_length=255, blank=True, default='', verbose_name="Nom de l’établissement complet")
    adresse_etablissement = models.CharField(max_length=255, blank=True, default='', verbose_name="Adresse complète de l’établissement")

    mention_legale = models.TextField(blank=True, null=True, verbose_name="Mention légale ou texte additionnel")
    qr_code = models.ImageField(upload_to='certificats/qrcodes/', storage=private_media_storage, blank=True, null=True, verbose_name="QR Code de vérification")
    code_verification = models.CharField(max_length=100, blank=True, null=True, unique=True, verbose_name="Code de vérification du document")

    statut = models.CharField(
        max_length=20,
        choices=[('valide', 'Valide'), ('annule', 'Annulé'), ('archive', 'Archivé')],
        default='valide',
        verbose_name="Statut du certificat"
    )
    remarque = models.TextField(blank=True, null=True, verbose_name="Remarque administrative")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Certificat de Fréquentation"
        verbose_name_plural = "Certificats de Fréquentation"
        unique_together = ('etudiant', 'annee_scolaire')
        ordering = ['-annee_scolaire', 'etudiant__nom']

    def __str__(self):
        return f"Certificat de {self.etudiant} ({self.annee_scolaire})"

    @property
    def nom_complet(self):
        return f"{self.etudiant.nom} {self.etudiant.prenom}"

    def is_valide(self):
        return self.statut == 'valide'

    def save(self, *args, **kwargs):
        if not self.numero_certificat:
            self.numero_certificat = f"CERT-{self.ecole_id}-{self.etudiant_id}-{self.annee_scolaire_id}"
        super().save(*args, **kwargs)

    



from django.db import models
# Assurez-vous d'importer vos modèles personnalisés (Classe, Matiere, Enseignant, AnneeScolaire)
# from .models import Classe, Matiere, Enseignant, AnneeScolaire 

class EmploiDuTemps(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings',
        on_delete=models.CASCADE,
        verbose_name="École",
    )
    class JourSemaine(models.TextChoices):
        LUNDI = 'Lundi', ('Lundi')
        MARDI = 'Mardi', ('Mardi')
        MERCREDI = 'Mercredi', ('Mercredi')
        JEUDI = 'Jeudi', ('Jeudi')
        VENDREDI = 'Vendredi', ('Vendredi')
        SAMEDI = 'Samedi', ('Samedi')

    classe = models.ForeignKey(Classe, on_delete=models.CASCADE, related_name='emplois_du_temps', verbose_name="Classe")
    jour = models.CharField(max_length=20, choices=JourSemaine.choices, verbose_name="Jour de la Semaine")
    
    # --- CHAMPS HEURES MODIFIÉS ---
    heure_debut = models.TimeField(verbose_name="Heure de Début")
    heure_fin = models.TimeField(verbose_name="Heure de Fin")
    # --- FIN CHAMPS HEURES MODIFIÉS ---
    emploiDuTemps = models.FileField(upload_to='emploiDuTemps/', blank=True, null=True, verbose_name="Fichier PDF demploi")

    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, verbose_name="Matière")
    enseignant = models.ForeignKey(Enseignant, on_delete=models.CASCADE, verbose_name="Enseignant")
    salle = models.ForeignKey('Salle', on_delete=models.SET_NULL, null=True, blank=True, related_name='emplois_du_temps', verbose_name="Salle de cours")
    annee_scolaire = models.ForeignKey(AnneeScolaire, on_delete=models.CASCADE, verbose_name="Année Scolaire")

    class Meta:
        # L'unicité est basée sur la classe, le jour et la PÉRIODE (début/fin) dans l'année scolaire
        unique_together = ('classe', 'jour', 'heure_debut', 'heure_fin', 'annee_scolaire')
        
        # Le tri doit être fait de manière séquentielle pour l'affichage dans un tableau
        ordering = ['classe', 'annee_scolaire', 'jour', 'heure_debut']

        verbose_name = "Emploi du Temps"
        verbose_name_plural = "Emplois du Temps"
        
    def __str__(self):
        # Affichage des heures au format HH:MM
        heure_str = f"{self.heure_debut.strftime('%H:%M')} - {self.heure_fin.strftime('%H:%M')}"
        return f"{self.classe.nom_classe} - {self.jour} {heure_str} : {self.matiere.nom}"

    # Vous pouvez ajouter une validation personnalisée pour s'assurer que heure_fin > heure_debut
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.heure_debut and self.heure_fin and self.heure_debut >= self.heure_fin:
            raise ValidationError("L'heure de fin doit être postérieure à l'heure de début.")





# ====================================================================
# MODÈLES DE DOCUMENTS PROPRES À CHAQUE ÉCOLE
# ====================================================================
import uuid
from django.core.validators import MaxLengthValidator
from .document_templates import DOCUMENT_TYPES, default_document_fields, validate_document_text


class ModeleDocument(models.Model):
    """Plan de document réutilisable par une école jusqu'à sa modification."""

    TYPE_BULLETIN = 'bulletin'
    TYPE_FREQUENTATION = 'frequentation'
    TYPE_ATTESTATION = 'attestation_scolarite'
    TYPE_INSCRIPTION = 'certificat_inscription'
    TYPE_AUTRE = 'autre'
    TYPE_CHOICES = DOCUMENT_TYPES

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='modeles_documents',
        verbose_name='École',
    )
    type_document = models.CharField(max_length=30, choices=TYPE_CHOICES, verbose_name='Type de document')
    code = models.SlugField(
        max_length=80, blank=True, default='',
        verbose_name='Code du modèle personnalisé',
        help_text='Obligatoire pour un document libre ; vide pour les documents standard.',
    )
    titre = models.CharField(max_length=180, verbose_name='Titre du document')
    entete = models.TextField(blank=True, validators=[MaxLengthValidator(1200)], verbose_name='En-tête')
    corps = models.TextField(blank=True, validators=[MaxLengthValidator(5000)], verbose_name='Texte principal')
    mention = models.TextField(blank=True, validators=[MaxLengthValidator(2000)], verbose_name='Mention')
    pied_de_page = models.TextField(blank=True, validators=[MaxLengthValidator(1200)], verbose_name='Pied de page')
    titre_signataire = models.CharField(max_length=100, blank=True, verbose_name='Titre du signataire')
    afficher_logo = models.BooleanField(default=True, verbose_name='Afficher le logo')
    afficher_cachet = models.BooleanField(default=True, verbose_name='Afficher le cachet')
    afficher_signature = models.BooleanField(default=True, verbose_name='Afficher la signature')
    actif = models.BooleanField(default=True, verbose_name='Modèle actif')
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Modèle de document'
        verbose_name_plural = 'Modèles de documents'
        ordering = ['type_document', 'titre']
        constraints = [
            models.UniqueConstraint(
                fields=['ecole', 'type_document', 'code'],
                name='uniq_modele_document_ecole_type_code',
            ),
        ]

    @classmethod
    def pour_ecole(cls, ecole, type_document, code=''):
        """Return saved layout or unsaved defaults; reading never inserts a row."""
        if type_document not in dict(cls.TYPE_CHOICES):
            raise ValueError('Type de document inconnu.')
        if type_document == cls.TYPE_AUTRE and not code:
            raise ValueError('Un code est nécessaire pour un modèle personnalisé.')
        if type_document != cls.TYPE_AUTRE and code:
            raise ValueError('Les documents standard ne possèdent pas de code.')
        ecole_id = getattr(ecole, 'pk', ecole)
        if ecole_id is None:
            raise ValueError('Une école enregistrée est nécessaire.')
        existing = cls.objects.filter(
            ecole_id=ecole_id, type_document=type_document, code=code,
        ).first()
        if existing:
            return existing
        defaults = default_document_fields(type_document)
        if isinstance(ecole, EcoleSettings):
            return cls(ecole=ecole, type_document=type_document, code=code, **defaults)
        return cls(ecole_id=ecole_id, type_document=type_document, code=code, **defaults)

    def clean(self):
        super().clean()
        errors = {}
        if self.type_document == self.TYPE_AUTRE:
            if not self.code:
                errors['code'] = 'Le code est obligatoire pour un document personnalisé.'
        elif self.code:
            errors['code'] = 'Le code est réservé aux documents personnalisés.'
        for field in ('titre', 'entete', 'corps', 'mention', 'pied_de_page', 'titre_signataire'):
            try:
                validate_document_text(getattr(self, field) or '')
            except ValidationError as exc:
                errors[field] = exc
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def as_snapshot(self):
        """Copy layout values so an issued document keeps its original plan."""
        fields = (
            'type_document', 'code', 'titre', 'entete', 'corps', 'mention',
            'pied_de_page', 'titre_signataire', 'afficher_logo',
            'afficher_cachet', 'afficher_signature',
        )
        return {'version': 1, **{field: getattr(self, field) for field in fields}}

    def __str__(self):
        return f'{self.titre} ({self.ecole.nom_etablissement})'


class DocumentEmis(models.Model):
    """Private PDF and immutable layout snapshot for a document already issued."""

    STATUT_VALIDE = 'valide'
    STATUT_ANNULE = 'annule'
    STATUT_CHOICES = ((STATUT_VALIDE, 'Valide'), (STATUT_ANNULE, 'Annulé'))

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.PROTECT, related_name='documents_emis', verbose_name='École',
    )
    etudiant = models.ForeignKey(
        Etudiant, on_delete=models.PROTECT, related_name='documents_emis', verbose_name='Élève',
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire, on_delete=models.PROTECT, related_name='documents_emis', verbose_name='Année scolaire',
    )
    inscription = models.ForeignKey(
        Inscription, on_delete=models.PROTECT, related_name='documents_emis',
        null=True, blank=True, verbose_name='Inscription annuelle',
    )
    modele = models.ForeignKey(
        ModeleDocument, on_delete=models.SET_NULL, related_name='documents_emis',
        null=True, blank=True, verbose_name='Modèle de document',
    )
    type_document = models.CharField(max_length=30, choices=ModeleDocument.TYPE_CHOICES)
    numero_document = models.CharField(max_length=80, unique=True, blank=True, verbose_name='Numéro du document')
    code_verification = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    fichier_pdf = models.FileField(
        upload_to='documents_emis/', storage=private_media_storage,
        blank=True, verbose_name='Fichier PDF privé',
    )
    modele_snapshot = models.JSONField(default=dict, blank=True, verbose_name='Plan lors de l’émission')
    donnees_snapshot = models.JSONField(default=dict, blank=True, verbose_name='Données lors de l’émission')
    emis_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Émis par',
    )
    date_emission = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default=STATUT_VALIDE)
    annule_le = models.DateTimeField(null=True, blank=True)
    annule_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='documents_annules', verbose_name='Annulé par',
    )
    motif_annulation = models.CharField(
        max_length=500, blank=True, verbose_name="Motif de l'annulation",
    )

    class Meta:
        verbose_name = 'Document émis'
        verbose_name_plural = 'Documents émis'
        ordering = ['-date_emission']
        indexes = [models.Index(fields=['ecole', 'etudiant', 'date_emission'], name='document_ecole_eleve_date_idx')]

    def capturer_modele(self, modele):
        """Bind the saved layout if possible and preserve its exact content."""
        if self.ecole_id and modele.ecole_id != self.ecole_id:
            raise ValidationError('Le modèle doit appartenir à la même école.')
        self.modele = modele if modele.pk else None
        self.type_document = modele.type_document
        self.modele_snapshot = modele.as_snapshot()

    def clean(self):
        super().clean()
        errors = {}
        if self.ecole_id and self.etudiant_id and self.etudiant.ecole_id != self.ecole_id:
            errors['etudiant'] = 'L’élève doit appartenir à la même école.'
        if self.ecole_id and self.annee_scolaire_id and self.annee_scolaire.ecole_id != self.ecole_id:
            errors['annee_scolaire'] = 'L’année doit appartenir à la même école.'
        if self.inscription_id:
            if self.inscription.ecole_id != self.ecole_id:
                errors['inscription'] = 'L’inscription doit appartenir à la même école.'
            elif self.inscription.etudiant_id != self.etudiant_id or self.inscription.annee_scolaire_id != self.annee_scolaire_id:
                errors['inscription'] = 'L’inscription doit correspondre à cet élève et cette année.'
        if self.modele_id:
            if self.modele.ecole_id != self.ecole_id:
                errors['modele'] = 'Le modèle doit appartenir à la même école.'
            elif self.modele.type_document != self.type_document:
                errors['type_document'] = 'Le type doit correspondre au modèle.'
        if self.modele_snapshot:
            if not isinstance(self.modele_snapshot, dict):
                errors['modele_snapshot'] = 'Le plan sauvegardé doit être un objet.'
            elif self.modele_snapshot.get('type_document') != self.type_document:
                errors['modele_snapshot'] = 'Le type du plan sauvegardé est incohérent.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.numero_document:
            if not self.ecole_id:
                raise ValidationError({'ecole': 'L’école est nécessaire pour numéroter le document.'})
            self.numero_document = f'DOC-{self.ecole_id}-{uuid.uuid4().hex[:16].upper()}'
        if self.modele_id and not self.modele_snapshot:
            self.modele_snapshot = self.modele.as_snapshot()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.numero_document} — {self.etudiant.prenom} {self.etudiant.nom}'


# ====================================================================
# ÉVALUATIONS DISTINCTES ET RÉSULTATS PAR INSCRIPTION
# ====================================================================
class Evaluation(models.Model):
    """Une épreuve d'une matière enseignée à une classe pendant un trimestre."""

    PERIODES_TRIMESTRIELLES = [
        ('Trimestre 1', 'Trimestre 1'),
        ('Trimestre 2', 'Trimestre 2'),
        ('Trimestre 3', 'Trimestre 3'),
    ]

    ecole = models.ForeignKey(EcoleSettings, on_delete=models.PROTECT, related_name='evaluations')
    programme = models.ForeignKey(ProgrammeMatiere, on_delete=models.PROTECT, related_name='evaluations')
    periode_evaluation = models.CharField(max_length=20, choices=PERIODES_TRIMESTRIELLES)
    titre = models.CharField(max_length=180, verbose_name="Titre de l'évaluation")
    type_evaluation = models.CharField(max_length=50, blank=True, verbose_name="Type d'évaluation")
    date_evaluation = models.DateField(verbose_name="Date de l'évaluation")
    bareme = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.01'))], verbose_name='Barème',
    )
    poids = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.01'))], verbose_name='Poids dans la matière',
    )
    cree_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='evaluations_creees', verbose_name='Créée par',
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Évaluation'
        verbose_name_plural = 'Évaluations'
        ordering = ['periode_evaluation', 'date_evaluation', 'pk']
        indexes = [models.Index(fields=['ecole', 'programme', 'periode_evaluation'], name='eval_ecole_programme_per_idx')]
        constraints = [
            models.CheckConstraint(condition=Q(bareme__gt=0), name='eval_bareme_positif'),
            models.CheckConstraint(condition=Q(poids__gt=0), name='eval_poids_positif'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.programme_id and self.ecole_id:
            programme = self.programme
            if (
                programme.ecole_id != self.ecole_id
                or programme.classe.ecole_id != self.ecole_id
                or programme.matiere.ecole_id != self.ecole_id
            ):
                errors['programme'] = "Le programme doit appartenir à l'école."
            elif self.date_evaluation:
                annee = programme.classe.annee_scolaire
                if not annee.date_debut <= self.date_evaluation <= annee.date_fin:
                    errors['date_evaluation'] = "La date doit appartenir à l'année scolaire de la classe."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.titre} — {self.programme.matiere.nom} ({self.programme.classe.nom_classe})'


class ResultatEvaluation(models.Model):
    """Note brute d'un élève pour une évaluation, sans écraser les autres épreuves."""

    evaluation = models.ForeignKey(Evaluation, on_delete=models.PROTECT, related_name='resultats')
    inscription = models.ForeignKey(Inscription, on_delete=models.PROTECT, related_name='resultats_evaluation')
    valeur = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Note obtenue',
    )
    annule = models.BooleanField(default=False, verbose_name='Résultat annulé')
    annule_le = models.DateTimeField(null=True, blank=True)
    annule_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resultats_evaluation_annules', verbose_name='Annulé par',
    )
    saisi_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resultats_evaluation_saisis', verbose_name='Saisi par',
    )
    modifie_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resultats_evaluation_modifies', verbose_name='Dernière modification par',
    )
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Résultat d'évaluation"
        verbose_name_plural = "Résultats d'évaluation"
        ordering = ['evaluation', 'inscription__etudiant__nom', 'inscription__etudiant__prenom']
        constraints = [
            models.UniqueConstraint(fields=['evaluation', 'inscription'], name='uniq_resultat_eval_inscription'),
            models.CheckConstraint(condition=Q(valeur__gte=0), name='resultat_valeur_non_negative'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.evaluation_id and self.inscription_id:
            evaluation = self.evaluation
            inscription = self.inscription
            programme = evaluation.programme
            if (
                evaluation.ecole_id != inscription.ecole_id
                or programme.ecole_id != evaluation.ecole_id
                or programme.classe.ecole_id != evaluation.ecole_id
                or inscription.etudiant.ecole_id != inscription.ecole_id
                or inscription.annee_scolaire_id != programme.classe.annee_scolaire_id
            ):
                errors['inscription'] = "L'élève doit appartenir à l'année et à l'école de l'évaluation."
            elif evaluation.date_evaluation:
                from parcours_scolaire.models import AffectationClasse

                if inscription.date_inscription > evaluation.date_evaluation:
                    errors['inscription'] = "L'élève n'était pas encore inscrit à la date de l'évaluation."
                elif not AffectationClasse.objects.filter(
                    inscription=inscription, classe_id=programme.classe_id,
                    date_debut__lte=evaluation.date_evaluation,
                ).filter(
                    Q(date_fin__gt=evaluation.date_evaluation) | Q(date_fin__isnull=True),
                ).exists():
                    errors['inscription'] = "L'élève n'était pas affecté à cette classe à la date de l'évaluation."
            if self.valeur is not None and self.valeur > evaluation.bareme:
                errors['valeur'] = 'La note ne peut pas dépasser le barème de l’évaluation.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.inscription.etudiant} : {self.valeur}/{self.evaluation.bareme}'


class RegleBulletinAnnuel(models.Model):
    """Pondération explicite des trimestres pour un cycle et une année scolaire."""

    CYCLE_CHOICES = [
        ('fondamental_1', 'Fondamental 1er cycle'),
        ('fondamental_2', 'Fondamental 2e cycle'),
        ('lycee', 'Lycée'),
    ]
    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.PROTECT, related_name='regles_bulletin_annuel',
        verbose_name='École',
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire, on_delete=models.PROTECT, related_name='regles_bulletin_annuel',
        verbose_name='Année scolaire',
    )
    cycle = models.CharField(max_length=20, choices=CYCLE_CHOICES, verbose_name='Cycle')
    poids_trimestre_1 = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Poids du 1er trimestre',
    )
    poids_trimestre_2 = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Poids du 2e trimestre',
    )
    poids_trimestre_3 = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(Decimal('0'))],
        verbose_name='Poids du 3e trimestre',
    )
    valide_par = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='regles_bulletin_annuel_validees', verbose_name='Validée par',
    )
    valide_le = models.DateTimeField(null=True, blank=True, verbose_name='Validée le')
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Règle de bulletin annuel'
        verbose_name_plural = 'Règles de bulletin annuel'
        ordering = ['-annee_scolaire__annee', 'cycle']
        constraints = [
            models.UniqueConstraint(
                fields=['ecole', 'annee_scolaire', 'cycle'],
                name='uniq_regle_bulletin_ecole_annee_cycle',
            ),
            models.CheckConstraint(
                condition=(Q(poids_trimestre_1__gte=0) & Q(poids_trimestre_2__gte=0) & Q(poids_trimestre_3__gte=0)),
                name='regle_bulletin_poids_non_negatifs',
            ),
            models.CheckConstraint(
                condition=(Q(poids_trimestre_1__gt=0) | Q(poids_trimestre_2__gt=0) | Q(poids_trimestre_3__gt=0)),
                name='regle_bulletin_somme_positive',
            ),
            models.CheckConstraint(
                condition=(Q(valide_par__isnull=True, valide_le__isnull=True)
                           | Q(valide_par__isnull=False, valide_le__isnull=False)),
                name='regle_bulletin_validation_complete',
            ),
        ]

    @property
    def est_validee(self):
        return self.valide_par_id is not None and self.valide_le is not None

    def clean(self):
        super().clean()
        errors = {}
        if self.ecole_id and self.annee_scolaire_id and self.annee_scolaire.ecole_id != self.ecole_id:
            errors['annee_scolaire'] = "L'année scolaire doit appartenir à la même école."
        poids = (self.poids_trimestre_1, self.poids_trimestre_2, self.poids_trimestre_3)
        if all(valeur is not None for valeur in poids) and sum(poids, Decimal('0')) <= 0:
            errors['poids_trimestre_1'] = 'La somme des poids doit être strictement positive.'
        if bool(self.valide_par_id) != bool(self.valide_le):
            errors['valide_par'] = 'La validation exige un auteur et une date.'
        if self.valide_par_id and self.ecole_id:
            auteur = self.valide_par
            profil = getattr(auteur, 'profile', None)
            if (profil is None or profil.ecole_id != self.ecole_id
                    or (not auteur.is_superuser and profil.role not in {'school_admin', 'director'})):
                errors['valide_par'] = "Seule la direction ou l'administration de l'école peut valider."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        champs_regle = (
            'ecole_id', 'annee_scolaire_id', 'cycle',
            'poids_trimestre_1', 'poids_trimestre_2', 'poids_trimestre_3',
        )
        update_fields = kwargs.get('update_fields')
        if self.pk and (update_fields is None or set(update_fields) & {
            'ecole', 'ecole_id', 'annee_scolaire', 'annee_scolaire_id', 'cycle',
            'poids_trimestre_1', 'poids_trimestre_2', 'poids_trimestre_3',
        }):
            precedente = type(self).objects.filter(pk=self.pk).values(*champs_regle).first()
            if precedente and any(getattr(self, champ) != precedente[champ] for champ in champs_regle):
                self.valide_par = None
                self.valide_le = None
                if update_fields is not None:
                    kwargs['update_fields'] = set(update_fields) | {'valide_par', 'valide_le'}
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_cycle_display()} — {self.annee_scolaire.annee}'


# ====================================================================
# INFRASTRUCTURE ET SALLES DE CLASSE
# ====================================================================

class Salle(models.Model):
    TYPE_SALLE_CHOICES = [
        ('standard', 'Salle de cours standard'),
        ('informatique', 'Salle informatique'),
        ('laboratoire', 'Laboratoire de sciences'),
        ('polyvalente', 'Salle polyvalente / Réunion'),
    ]

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='salles', verbose_name="École",
    )
    nom_salle = models.CharField(max_length=50, verbose_name="Nom de la salle")
    code_salle = models.CharField(max_length=20, blank=True, null=True, verbose_name="Code de la salle")
    capacite = models.PositiveSmallIntegerField(default=50, verbose_name="Capacité")
    type_salle = models.CharField(
        max_length=30, choices=TYPE_SALLE_CHOICES, default='standard', verbose_name="Type de salle",
    )

    class Meta:
        verbose_name = "Salle de classe"
        verbose_name_plural = "Salles de classe"
        ordering = ['nom_salle']
        constraints = [
            models.UniqueConstraint(fields=['ecole', 'nom_salle'], name='uniq_salle_nom_par_ecole'),
        ]

    def __str__(self):
        return f"{self.nom_salle} ({self.capacite} places)"


class PlanEcheancier(models.Model):
    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='plans_echeancier', verbose_name="École",
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire, on_delete=models.CASCADE, related_name='plans_echeancier', verbose_name="Année scolaire",
    )
    classe = models.ForeignKey(
        Classe, on_delete=models.CASCADE, null=True, blank=True,
        related_name='plans_echeancier', verbose_name="Classe ciblée (vide = tout l'établissement)",
    )
    nom_tranche = models.CharField(max_length=100, verbose_name="Intitulé de la tranche")
    motif = models.CharField(
        max_length=100, choices=Paiement.MOTIF_PAIEMENT_CHOICES, default='Frais de Scolarité', verbose_name="Motif",
    )
    montant = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant exigible (FCFA)",
    )
    date_echeance = models.DateField(verbose_name="Date limite d'exigibilité")
    ordre = models.PositiveSmallIntegerField(default=1, verbose_name="Ordre d'échéance")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Plan d'échéancier scolaire"
        verbose_name_plural = "Plans d'échéanciers scolaires"
        ordering = ['ordre', 'date_echeance', 'nom_tranche']

    def __str__(self):
        return f"{self.nom_tranche} - {self.montant} FCFA ({self.date_echeance.strftime('%d/%m/%Y')})"


# ====================================================================
# TUTEURS, PARENTS ET RELATIONS FAMILIALES
# ====================================================================

class Tuteur(models.Model):
    CIVILITE_CHOICES = [('M.', 'Monsieur'), ('Mme', 'Madame'), ('Mlle', 'Mademoiselle')]
    CANAL_CHOICES = [
        ('sms', 'SMS Mobile'),
        ('whatsapp', 'WhatsApp'),
        ('appel', 'Appel téléphonique'),
        ('email', 'Email'),
    ]

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='tuteurs', verbose_name="École",
    )
    civilite = models.CharField(max_length=10, choices=CIVILITE_CHOICES, default='M.', verbose_name="Civilité")
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom(s)")
    profession = models.CharField(max_length=100, blank=True, verbose_name="Profession")
    telephone_principal = models.CharField(max_length=30, verbose_name="Téléphone principal")
    telephone_secondaire = models.CharField(max_length=30, blank=True, verbose_name="Téléphone secondaire")
    email = models.EmailField(blank=True, verbose_name="Adresse email")
    adresse = models.CharField(max_length=200, blank=True, verbose_name="Adresse")
    quartier = models.CharField(max_length=100, blank=True, default='Bamako', verbose_name="Quartier / Commune")
    canal_prefere = models.CharField(
        max_length=20, choices=CANAL_CHOICES, default='sms', verbose_name="Canal de communication favori",
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tuteur / Parent d'élève"
        verbose_name_plural = "Tuteurs / Parents d'élèves"
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.civilite} {self.prenom} {self.nom} ({self.telephone_principal})"


class LienTuteur(models.Model):
    LIEN_CHOICES = [
        ('pere', 'Père'),
        ('mere', 'Mère'),
        ('tuteur_legal', 'Tuteur légal'),
        ('oncle', 'Oncle'),
        ('tante', 'Tante'),
        ('grand_parent', 'Grand-parent'),
        ('autre', 'Autre responsable'),
    ]

    tuteur = models.ForeignKey(Tuteur, on_delete=models.CASCADE, related_name='liens_etudiants')
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name='liens_tuteurs')
    lien_parente = models.CharField(max_length=30, choices=LIEN_CHOICES, default='pere', verbose_name="Lien de parenté")
    est_responsable_financier = models.BooleanField(default=True, verbose_name="Responsable financier (paiements)")
    est_contact_urgence = models.BooleanField(default=True, verbose_name="Contact en cas d'absence ou urgence")
    recoit_bulletin = models.BooleanField(default=True, verbose_name="Destinataire du bulletin")

    class Meta:
        verbose_name = "Lien de parenté élève-tuteur"
        verbose_name_plural = "Liens de parenté élèves-tuteurs"
        constraints = [
            models.UniqueConstraint(fields=['tuteur', 'etudiant'], name='uniq_lien_tuteur_etudiant'),
        ]

    def __str__(self):
        return f"{self.tuteur} - {self.get_lien_parente_display()} de {self.etudiant}"


# ====================================================================
# DÉLIBÉRATIONS DU CONSEIL DE CLASSE ET NOTIFICATIONS PARENTS
# ====================================================================

class DecisionConseilClasse(models.Model):
    PERIODE_CHOICES = [
        ('Trimestre 1', 'Trimestre 1'),
        ('Trimestre 2', 'Trimestre 2'),
        ('Trimestre 3', 'Trimestre 3'),
        ('Annuelle', 'Bilan Annuel'),
        ('Annuel', 'Bilan Annuel'),
    ]
    MENTION_CHOICES = [
        ('tres_bien', 'Félicitations - Mention Très Bien (>=16)'),
        ('bien', 'Félicitations - Mention Bien (>=14)'),
        ('assez_bien', 'Compliments - Mention Assez Bien (>=12)'),
        ('passable', 'Encouragements - Mention Passable (>=10)'),
        ('tableau_honneur', 'Tableau d’Honneur'),
        ('avertissement', 'Avertissement de travail (<10)'),
        ('blame', 'Blâme de travail (<8)'),
        ('Tres Bien', 'Félicitations - Mention Très Bien (>=16)'),
        ('Bien', 'Félicitations - Mention Bien (>=14)'),
        ('Assez Bien', 'Compliments - Mention Assez Bien (>=12)'),
        ('Passable', 'Encouragements - Mention Passable (>=10)'),
        ('Tableau Honneur', 'Tableau d’Honneur'),
        ('Avertissement', 'Avertissement de travail (<10)'),
        ('Blame', 'Blâme de travail (<8)'),
    ]
    DECISION_PASSAGE_CHOICES = [
        ('admis', 'Admis(e) en classe supérieure'),
        ('redouble', 'Redouble la classe'),
        ('exclu', 'Exclu(e)'),
        ('admis_examen', 'Admis(e) à se présenter aux examens nationaux (DEF / BAC)'),
        ('en_attente', 'En attente de délibération'),
    ]

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='decisions_conseil', verbose_name="École",
    )
    inscription = models.ForeignKey(
        Inscription, on_delete=models.CASCADE, related_name='decisions_conseil', verbose_name="Inscription",
    )
    periode = models.CharField(max_length=20, choices=PERIODE_CHOICES, verbose_name="Période")
    moyenne = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Moyenne obtenue")
    rang = models.PositiveIntegerField(verbose_name="Rang dans la classe")
    effectif = models.PositiveIntegerField(verbose_name="Effectif de la classe")
    moyenne_classe = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Moyenne de la classe")
    moyenne_max = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Plus forte moyenne")
    moyenne_min = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Plus faible moyenne")
    mention = models.CharField(max_length=50, blank=True, choices=MENTION_CHOICES, verbose_name="Mention")
    decision_passage = models.CharField(
        max_length=30, blank=True, null=True, choices=DECISION_PASSAGE_CHOICES, verbose_name="Décision du conseil",
    )
    total_absences = models.PositiveIntegerField(default=0, verbose_name="Total absences")
    total_retards = models.PositiveIntegerField(default=0, verbose_name="Total retards")
    observations = models.TextField(blank=True, verbose_name="Observations du conseil")
    valide_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Président du conseil",
    )
    date_validation = models.DateTimeField(default=timezone.now, verbose_name="Date de délibération")

    class Meta:
        verbose_name = "Décision du Conseil de Classe"
        verbose_name_plural = "Décisions des Conseils de Classe"
        ordering = ['-date_validation', 'rang']
        unique_together = [('inscription', 'periode')]

    def __str__(self):
        return f"{self.inscription.etudiant} - {self.periode} : {self.moyenne}/20 (Rang {self.rang}e)"


class NotificationParent(models.Model):
    EVENEMENT_CHOICES = [
        ('absence', 'Avis d’absence'),
        ('retard', 'Notification de retard'),
        ('rappel_paiement', 'Rappel d’échéance de scolarité'),
        ('recu_paiement', 'Reçu de paiement sécurisé'),
        ('bulletin', 'Mise à disposition du bulletin'),
        ('general', 'Information générale'),
    ]
    CANAL_CHOICES = [('sms', 'SMS Mobile'), ('whatsapp', 'WhatsApp'), ('email', 'Email')]
    STATUT_CHOICES = [
        ('en_attente', 'En attente d’envoi'),
        ('envoye', 'Envoyé avec succès'),
        ('echec', 'Échec de transmission'),
    ]

    ecole = models.ForeignKey(
        EcoleSettings, on_delete=models.CASCADE, related_name='notifications_parents', verbose_name="École",
    )
    tuteur = models.ForeignKey(
        Tuteur, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications',
        verbose_name="Tuteur destinataire",
    )
    etudiant = models.ForeignKey(
        Etudiant, on_delete=models.CASCADE, related_name='notifications_parents', verbose_name="Élève concerné",
    )
    type_evenement = models.CharField(max_length=30, choices=EVENEMENT_CHOICES, verbose_name="Type d’événement")
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES, default='sms', verbose_name="Canal")
    destinataire = models.CharField(max_length=100, verbose_name="Destinataire (N° Tél. ou Email)")
    message = models.TextField(verbose_name="Contenu du message")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='envoye', verbose_name="Statut")
    reference_externe = models.CharField(max_length=100, blank=True, verbose_name="Réf. Passerelle SMS/WhatsApp")
    envoye_le = models.DateTimeField(default=timezone.now, verbose_name="Date d’envoi")
    declenche_par = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Déclenché par",
    )

    class Meta:
        verbose_name = "Notification Parent"
        verbose_name_plural = "Notifications Parents"
        ordering = ['-envoye_le']

    def __str__(self):
        return f"Notification {self.get_canal_display()} à {self.destinataire} ({self.get_type_evenement_display()})"


# ====================================================================
# COMPTABILITÉ & JOURNAL DE CAISSE D'ÉTABLISSEMENT
# ====================================================================

class Depense(models.Model):
    CATEGORIE_CHOICES = [
        ('salaire', 'Vacations & Salaires enseignants'),
        ('fournitures', 'Fournitures & Matériel pédagogique (craies, rames, cahiers)'),
        ('energie_eau', 'Factures EDM (Électricité) & SOMAGEP (Eau)'),
        ('carburant', 'Carburant groupe électrogène / transport'),
        ('loyer', 'Loyer du bâtiment scolaire'),
        ('maintenance', 'Entretien, réparations & maintenance'),
        ('apem', 'Activités périscolaires & sportives'),
        ('autre', 'Autre dépense administrative'),
    ]
    MODE_PAIEMENT_CHOICES = [
        ('Espèces', 'Espèces'),
        ('Orange Money', 'Orange Money Mali'),
        ('Wave', 'Wave Mali'),
        ('Moov Money', 'Moov Africa Malitel'),
        ('Sama Money', 'Sama Money'),
        ('Chèque', 'Chèque'),
        ('Virement Bancaire', 'Virement Bancaire'),
    ]

    ecole = models.ForeignKey(
        'EcoleSettings', on_delete=models.CASCADE, related_name='depenses', verbose_name="École",
    )
    annee_scolaire = models.ForeignKey(
        'AnneeScolaire', on_delete=models.CASCADE, related_name='depenses', verbose_name="Année Scolaire",
    )
    categorie = models.CharField(max_length=50, choices=CATEGORIE_CHOICES, verbose_name="Catégorie de dépense")
    libelle = models.CharField(max_length=200, verbose_name="Libellé / Objet")
    montant = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Montant Décaissé (FCFA)",
    )
    beneficiaire = models.CharField(max_length=150, verbose_name="Bénéficiaire / Fournisseur")
    date_depense = models.DateField(default=timezone.now, verbose_name="Date de Décaissement")
    mode_paiement = models.CharField(max_length=50, choices=MODE_PAIEMENT_CHOICES, default='Espèces', verbose_name="Mode de Règlement")
    reference_piece = models.CharField(max_length=100, blank=True, null=True, verbose_name="N° Facture / Reçu / Pièce justificative")
    enregistre_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Enregistré par")
    observations = models.TextField(blank=True, null=True, verbose_name="Observations")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dépense d'établissement"
        verbose_name_plural = "Dépenses d'établissement"
        ordering = ['-date_depense', '-cree_le']

    def __str__(self):
        return f"{self.libelle} - {self.montant:,.0f} FCFA ({self.get_categorie_display()})"


class ClotureCaisse(models.Model):
    ecole = models.ForeignKey(
        'EcoleSettings', on_delete=models.CASCADE, related_name='clotures_caisse', verbose_name="École",
    )
    date_cloture = models.DateField(default=timezone.now, verbose_name="Date de clôture")
    total_encaissements = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Total Encaissements (FCFA)")
    total_decaissements = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Total Décaissements (FCFA)")
    solde_net_theorique = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Solde Net Théorique (FCFA)")
    solde_physique_compte = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Solde Physique Compté (FCFA)")
    ecart = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Écart de Caisse (FCFA)")
    statut = models.CharField(
        max_length=20,
        choices=[('conforme', 'Caisse Conforme'), ('ecart_justifie', 'Écart Justifié'), ('anomalie', 'Anomalie')],
        default='conforme',
        verbose_name="Statut de la caisse",
    )
    cloture_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Clôturé par")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes de clôture")
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Clôture de Caisse"
        verbose_name_plural = "Clôtures de Caisse"
        unique_together = ('ecole', 'date_cloture')
        ordering = ['-date_cloture']

    def save(self, *args, **kwargs):
        self.solde_net_theorique = (self.total_encaissements or Decimal('0.00')) - (self.total_decaissements or Decimal('0.00'))
        if self.solde_physique_compte is not None:
            self.ecart = self.solde_physique_compte - self.solde_net_theorique
            if self.ecart == Decimal('0.00'):
                self.statut = 'conforme'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Caisse {self.date_cloture} - Solde : {self.solde_net_theorique:,.0f} FCFA ({self.get_statut_display()})"
