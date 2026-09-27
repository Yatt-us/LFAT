"""Historique daté des classes d'une inscription annuelle."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q


class AffectationClasse(models.Model):
    class Origine(models.TextChoices):
        SAISIE = 'saisie', 'Saisie datée'
        REPRISE = 'reprise', 'Reprise des données existantes'

    inscription = models.ForeignKey(
        'dashboard.Inscription', on_delete=models.PROTECT, related_name='affectations_classe',
    )
    classe = models.ForeignKey(
        'dashboard.Classe', on_delete=models.PROTECT, related_name='affectations_eleves',
    )
    date_debut = models.DateField(verbose_name='Début inclus')
    date_fin = models.DateField(null=True, blank=True, verbose_name='Fin exclue')
    origine = models.CharField(max_length=10, choices=Origine.choices, default=Origine.SAISIE)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='affectations_classe_creees', verbose_name='Créée par',
    )
    termine_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='affectations_classe_terminees', verbose_name='Terminée par',
    )
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Affectation de classe'
        verbose_name_plural = 'Affectations de classe'
        ordering = ['inscription', 'date_debut']
        indexes = [
            models.Index(fields=['inscription', 'date_debut'], name='affect_insc_debut_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gt=F('date_debut')),
                name='affectation_intervalle_positif',
            ),
            models.UniqueConstraint(
                fields=['inscription'], condition=Q(date_fin__isnull=True),
                name='uniq_affectation_ouverte_insc',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.inscription_id and self.classe_id:
            if (self.classe.ecole_id != self.inscription.ecole_id or
                    self.classe.annee_scolaire_id != self.inscription.annee_scolaire_id or
                    self.inscription.etudiant.ecole_id != self.inscription.ecole_id):
                errors['classe'] = "La classe doit appartenir à l'école et à l'année de l'inscription."
        if self.inscription_id and self.date_debut:
            annee = self.inscription.annee_scolaire
            if not max(self.inscription.date_inscription, annee.date_debut) <= self.date_debut <= annee.date_fin:
                errors['date_debut'] = "Le début doit suivre l'inscription et appartenir à son année scolaire."
        if self.date_debut and self.date_fin and self.date_fin <= self.date_debut:
            errors['date_fin'] = 'La fin doit être postérieure au début (fin exclue).'
        if self.inscription_id and self.date_debut and not errors:
            autres = AffectationClasse.objects.filter(inscription_id=self.inscription_id).exclude(pk=self.pk)
            if self.date_fin:
                autres = autres.filter(date_debut__lt=self.date_fin)
            autres = autres.filter(Q(date_fin__isnull=True) | Q(date_fin__gt=self.date_debut))
            if autres.exists():
                errors['date_debut'] = "Cette période chevauche une autre affectation de l'inscription."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Sérialiser les écritures d'une même inscription avant de tester les intervalles.
        from dashboard.models import Inscription
        with transaction.atomic():
            if self.inscription_id:
                Inscription.objects.select_for_update().get(pk=self.inscription_id)
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        fin = self.date_fin.isoformat() if self.date_fin else 'en cours'
        return f'{self.inscription.etudiant} · {self.classe.nom_classe} · {self.date_debut} → {fin}'
