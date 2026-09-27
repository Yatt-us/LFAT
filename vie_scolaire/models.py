"""Pointage daté par séance, distinct du registre journalier historique."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Seance(models.Model):
    ecole = models.ForeignKey('dashboard.EcoleSettings', on_delete=models.PROTECT, related_name='seances')
    classe = models.ForeignKey('dashboard.Classe', on_delete=models.PROTECT, related_name='seances')
    programme = models.ForeignKey('dashboard.ProgrammeMatiere', on_delete=models.PROTECT, related_name='seances')
    enseignant = models.ForeignKey('dashboard.Enseignant', on_delete=models.PROTECT, related_name='seances')
    date = models.DateField(verbose_name='Date du cours')
    heure_debut = models.TimeField(verbose_name='Début')
    heure_fin = models.TimeField(verbose_name='Fin')
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Séance'
        verbose_name_plural = 'Séances'
        ordering = ['-date', 'heure_debut', 'classe__nom_classe']
        indexes = [
            models.Index(fields=['ecole', 'date', 'classe'], name='seance_ecole_date_classe_idx'),
            models.Index(fields=['ecole', 'date', 'enseignant'], name='seance_ecole_date_prof_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(heure_debut__lt=F('heure_fin')), name='seance_heures_croissantes'),
            models.UniqueConstraint(fields=['classe', 'date', 'heure_debut'], name='uniq_seance_classe_debut'),
            models.UniqueConstraint(fields=['enseignant', 'date', 'heure_debut'], name='uniq_seance_prof_debut'),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.ecole_id and self.classe_id and self.classe.ecole_id != self.ecole_id:
            errors['programme'] = "La classe doit appartenir à l'école."
        if self.ecole_id and self.programme_id:
            if self.programme.ecole_id != self.ecole_id or self.programme.classe_id != self.classe_id:
                errors['programme'] = "Le programme doit appartenir à cette classe et à cette école."
            elif self.programme.enseignant_id is None:
                errors['programme'] = "Affectez un enseignant au programme avant de créer la séance."
            elif self.enseignant_id and self.programme.enseignant_id != self.enseignant_id:
                errors['programme'] = "L'enseignant doit être celui affecté au programme."
        if self.ecole_id and self.enseignant_id and self.enseignant.ecole_id != self.ecole_id:
            errors['programme'] = "L'enseignant doit appartenir à l'école."
        if self.classe_id and self.date:
            annee = self.classe.annee_scolaire
            if not annee.date_debut <= self.date <= annee.date_fin:
                errors['date'] = "La séance doit se situer dans l'année scolaire de la classe."
        if self.heure_debut and self.heure_fin:
            if self.heure_debut >= self.heure_fin:
                errors['heure_fin'] = "L'heure de fin doit suivre l'heure de début."
            elif self.ecole_id and self.date and self.classe_id and self.enseignant_id:
                chevauchements = Seance.objects.filter(
                    ecole_id=self.ecole_id, date=self.date,
                    heure_debut__lt=self.heure_fin, heure_fin__gt=self.heure_debut,
                ).exclude(pk=self.pk)
                if chevauchements.filter(classe_id=self.classe_id).exists():
                    errors['heure_debut'] = 'Un autre cours de cette classe chevauche cette séance.'
                if chevauchements.filter(enseignant_id=self.enseignant_id).exists():
                    errors['programme'] = 'Cet enseignant a déjà un cours sur cette plage horaire.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.classe.nom_classe} · {self.programme.matiere.nom} · {self.date} {self.heure_debut:%H:%M}'


class Pointage(models.Model):
    class Statut(models.TextChoices):
        PRESENT = 'present', 'Présent'
        ABSENT = 'absent', 'Absent'
        RETARD = 'retard', 'Retard'

    seance = models.ForeignKey(Seance, on_delete=models.PROTECT, related_name='pointages')
    inscription = models.ForeignKey('dashboard.Inscription', on_delete=models.PROTECT, related_name='pointages_seance')
    statut = models.CharField(max_length=10, choices=Statut.choices)
    minutes_retard = models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Minutes de retard')
    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pointage de séance'
        verbose_name_plural = 'Pointages de séance'
        ordering = ['inscription__etudiant__nom', 'inscription__etudiant__prenom']
        constraints = [
            models.UniqueConstraint(fields=['seance', 'inscription'], name='uniq_pointage_seance_inscription'),
            models.CheckConstraint(
                condition=(Q(statut='retard', minutes_retard__gt=0) |
                           Q(statut__in=['present', 'absent'], minutes_retard__isnull=True)),
                name='pointage_retard_minutes_coherentes',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.seance_id and self.inscription_id:
            seance = self.seance
            inscription = self.inscription
            if (inscription.ecole_id != seance.ecole_id or
                    inscription.etudiant.ecole_id != seance.ecole_id or
                    inscription.annee_scolaire_id != seance.classe.annee_scolaire_id):
                errors['inscription'] = "L'inscription doit appartenir à l'année et à l'école de la séance."
            elif inscription.date_inscription > seance.date:
                errors['inscription'] = "L'élève n'était pas encore inscrit à la date de la séance."
            else:
                from parcours_scolaire.models import AffectationClasse
                affectee = AffectationClasse.objects.filter(
                    inscription=inscription, classe_id=seance.classe_id,
                    date_debut__lte=seance.date,
                ).filter(Q(date_fin__gt=seance.date) | Q(date_fin__isnull=True)).exists()
                # Les anciens pointages importés restent corrigeables, sans autoriser
                # une nouvelle présence hors d'une affectation datée.
                pointage_ancien = self.pk and Pointage.objects.filter(
                    pk=self.pk, seance=seance, inscription=inscription,
                ).exists()
                if not affectee and not pointage_ancien:
                    errors['inscription'] = "L'élève n'était pas affecté à cette classe à la date de la séance."
        if self.statut == self.Statut.RETARD:
            if not self.minutes_retard or self.minutes_retard <= 0:
                errors['minutes_retard'] = 'Indiquez un nombre positif de minutes de retard.'
        elif self.minutes_retard is not None:
            errors['minutes_retard'] = 'Les minutes sont réservées au statut Retard.'
        if self.pk and self.statut == self.Statut.PRESENT and Justification.objects.filter(pointage_id=self.pk).exists():
            errors['statut'] = 'Ce pointage possède une justification ; sa correction nécessite une revue administrative.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.inscription.etudiant} · {self.seance.date} · {self.get_statut_display()}'


class Justification(models.Model):
    class Etat(models.TextChoices):
        ATTENTE = 'en_attente', 'En attente'
        VALIDEE = 'validee', 'Validée'
        REFUSEE = 'refusee', 'Refusée'

    pointage = models.OneToOneField(Pointage, on_delete=models.PROTECT, related_name='justification')
    motif = models.TextField(verbose_name='Motif communiqué')
    etat = models.CharField(max_length=12, choices=Etat.choices, default=Etat.ATTENTE)
    soumis_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='justifications_soumises')
    soumis_le = models.DateTimeField(auto_now_add=True)
    decide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='justifications_decidees')
    decide_le = models.DateTimeField(null=True, blank=True)
    commentaire_decision = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Justification de présence'
        verbose_name_plural = 'Justifications de présence'
        ordering = ['-soumis_le']

    def clean(self):
        super().clean()
        errors = {}
        if self.pointage_id and self.pointage.statut not in {Pointage.Statut.ABSENT, Pointage.Statut.RETARD}:
            errors['__all__'] = 'Une justification concerne une absence ou un retard.'
        if not (self.motif or '').strip():
            errors['motif'] = 'Saisissez un motif.'
        if self.etat == self.Etat.ATTENTE:
            if self.decide_par_id or self.decide_le:
                errors['__all__'] = 'Une justification en attente ne peut pas avoir de décision.'
        elif not self.decide_par_id or not self.decide_le:
            errors['__all__'] = 'Une décision exige son auteur et sa date.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.pointage} · {self.get_etat_display()}'


class EntreeCahierTexte(models.Model):
    """Cahier de texte numérique consignant le déroulement d'une séance et les devoirs."""
    class StatutVisa(models.TextChoices):
        EN_ATTENTE = 'en_attente', 'En attente de visa'
        VISE = 'vise', 'Visé par la Direction'
        OBSERVATIONS = 'observations', 'Visé avec observations'

    seance = models.OneToOneField(Seance, on_delete=models.CASCADE, related_name='cahier_de_texte', verbose_name="Séance de cours")
    titre_lecon = models.CharField(max_length=200, verbose_name="Titre de la leçon / Chapitre")
    resume_cours = models.TextField(verbose_name="Contenu du cours & Activités réalisées")
    devoirs_a_faire = models.TextField(blank=True, null=True, verbose_name="Travail à faire / Devoirs à la maison")
    date_limite_devoir = models.DateField(blank=True, null=True, verbose_name="Date d'échéance du devoir")
    statut_visa = models.CharField(max_length=20, choices=StatutVisa.choices, default=StatutVisa.EN_ATTENTE, verbose_name="Visa Direction")
    vise_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='visas_cahier_texte', verbose_name="Visé par")
    date_visa = models.DateTimeField(null=True, blank=True, verbose_name="Date du visa")
    observations_visa = models.TextField(blank=True, null=True, verbose_name="Observations pédagogiques")
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Entrée du cahier de texte"
        verbose_name_plural = "Cahier de texte numérique"
        ordering = ['-seance__date', '-seance__heure_debut']

    def __str__(self):
        return f"{self.seance.classe.nom_classe} - {self.seance.programme.matiere.nom} : {self.titre_lecon}"
