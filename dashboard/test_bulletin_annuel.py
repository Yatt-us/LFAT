"""Règle annuelle propre à chaque école, année et cycle scolaire."""

from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .academic_calculations import BulletinCalculationError, bulletin_annuel
from .models import (
    AnneeScolaire, Classe, DocumentEmis, EcoleSettings, Etudiant, Inscription,
    Matiere, Note, Profile, ProgrammeMatiere, RegleBulletinAnnuel,
)
from .private_media import private_media_storage
from parcours_scolaire.models import AffectationClasse


class BulletinAnnuelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École règle annuelle')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee,
            nom_classe='8e A', niveau='8AP',
        )
        cls.eleve = Etudiant.objects.create(
            ecole=cls.ecole, nom='Exemple', prenom='Calcul',
            date_naissance=date(2010, 1, 1), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        cls.inscription = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve,
            annee_scolaire=cls.annee, classe=cls.classe,
            date_inscription=date(2026, 9, 1),
        )
        cls.francais = Matiere.objects.create(ecole=cls.ecole, nom='Français')
        cls.maths = Matiere.objects.create(ecole=cls.ecole, nom='Mathématiques')
        ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.francais, coefficient=1,
        )
        ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.maths, coefficient=2,
        )
        cls.directeur = User.objects.create_user(username='directeur_regle', password='unused')
        Profile.objects.create(user=cls.directeur, ecole=cls.ecole, role='director')
        for periode, jour, francais in (
            ('Trimestre 1', date(2026, 10, 1), '10.00'),
            ('Trimestre 2', date(2027, 2, 1), '12.00'),
            ('Trimestre 3', date(2027, 5, 1), '16.00'),
        ):
            for matiere, valeur in ((cls.francais, francais), (cls.maths, '14.00')):
                Note.objects.create(
                    ecole=cls.ecole, etudiant=cls.eleve, matiere=matiere,
                    annee_scolaire=cls.annee, periode_evaluation=periode,
                    valeur=Decimal(valeur), date_evaluation=jour,
                )

    def setUp(self):
        self.client.force_login(self.directeur)
        self.url = reverse('generer_bulletin_scolaire', args=[self.eleve.pk, 'Annuelle'])

    def _regle(self, *, cycle='fondamental_2', validated=True):
        return RegleBulletinAnnuel.objects.create(
            ecole=self.ecole, annee_scolaire=self.annee, cycle=cycle,
            poids_trimestre_1=Decimal('1.00'),
            poids_trimestre_2=Decimal('1.00'),
            poids_trimestre_3=Decimal('2.00'),
            valide_par=self.directeur if validated else None,
            valide_le=timezone.now() if validated else None,
        )

    def test_absent_or_unvalidated_rule_blocks_annual_bulletin(self):
        self.assertEqual(self.client.get(self.url).status_code, 409)
        self._regle(validated=False)
        self.assertEqual(self.client.get(self.url).status_code, 409)
        self.assertFalse(DocumentEmis.objects.exists())

    def test_validated_cycle_weights_produce_complete_annual_average(self):
        self._regle()
        rows, moyenne = bulletin_annuel(self.inscription)
        self.assertEqual(moyenne, '13.83')
        self.assertEqual({row['matiere']: row['valeur'] for row in rows}, {
            'Français': '13.50', 'Mathématiques': '14.00',
        })
        preview = self.client.get(self.url)
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, '13.83')
        self.assertFalse(DocumentEmis.objects.exists())

    def test_missing_required_period_blocks_even_with_rule(self):
        self._regle()
        Note.objects.filter(matiere=self.francais, periode_evaluation='Trimestre 3').delete()
        with self.assertRaisesMessage(BulletinCalculationError, 'Français'):
            bulletin_annuel(self.inscription)
        self.assertEqual(self.client.post(self.url).status_code, 409)

    def test_rule_for_other_cycle_does_not_apply(self):
        self._regle(cycle='lycee')
        self.assertEqual(self.client.get(self.url).status_code, 409)

    def test_modifying_weights_requires_new_validation(self):
        regle = self._regle()
        regle.poids_trimestre_3 = Decimal('3.00')
        regle.save()
        regle.refresh_from_db()
        self.assertFalse(regle.est_validee)
        self.assertEqual(self.client.get(self.url).status_code, 409)

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 annuelle-test')
    def test_published_annual_snapshot_includes_validated_policy(self, _render):
        regle = self._regle()
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        storage_patch = patch.object(private_media_storage, 'location', temp.name)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        document = DocumentEmis.objects.get()
        self.assertEqual(document.donnees_snapshot['moyenne'], '13.83')
        self.assertTrue(all(
            row['regle_bulletin_id'] == regle.pk
            for row in document.donnees_snapshot['notes']
        ))

    def test_legacy_direct_annual_note_blocks_conflicting_calculation(self):
        self._regle()
        Note.objects.create(
            ecole=self.ecole, etudiant=self.eleve, matiere=self.francais,
            annee_scolaire=self.annee, periode_evaluation='Annuelle',
            valeur=Decimal('19.00'), date_evaluation=date(2027, 5, 10),
        )
        with self.assertRaisesMessage(BulletinCalculationError, 'notes annuelles anciennes'):
            bulletin_annuel(self.inscription)
        self.assertEqual(self.client.get(self.url).status_code, 409)

    def test_class_transfer_blocks_publication_without_transfer_rule(self):
        self._regle()
        ancienne = Classe.objects.create(
            ecole=self.ecole, annee_scolaire=self.annee,
            nom_classe='8e B', niveau='8AP',
        )
        AffectationClasse.objects.create(
            inscription=self.inscription, classe=ancienne,
            date_debut=date(2026, 9, 1), date_fin=date(2026, 12, 1),
        )
        AffectationClasse.objects.create(
            inscription=self.inscription, classe=self.classe,
            date_debut=date(2026, 12, 1),
        )
        with self.assertRaisesMessage(BulletinCalculationError, 'classe de cet élève a changé'):
            bulletin_annuel(self.inscription)
        self.assertEqual(self.client.get(self.url).status_code, 409)
