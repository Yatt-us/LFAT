"""Contrôles de complétude avant l'émission des bulletins."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from .academic_calculations import BulletinCalculationError, bulletin_trimestriel, moyenne_ponderee
from .models import (
    AnneeScolaire, Classe, EcoleSettings, Etudiant, Inscription, Matiere,
    Note, Profile, ProgrammeMatiere,
)


class BulletinCalculationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École bulletin')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee,
            nom_classe='6e A', niveau='6AP',
        )
        cls.eleve = Etudiant.objects.create(
            ecole=cls.ecole, nom='Traoré', prenom='Awa',
            date_naissance=date(2013, 3, 15), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        cls.inscription = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve,
            annee_scolaire=cls.annee, classe=cls.classe,
        )
        cls.francais = Matiere.objects.create(ecole=cls.ecole, nom='Français')
        cls.maths = Matiere.objects.create(ecole=cls.ecole, nom='Mathématiques')
        cls.programme_francais = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.francais, coefficient=1,
        )
        cls.programme_maths = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.maths, coefficient=2,
        )
        cls.user = User.objects.create_user(username='bulletin_directeur', password='unused')
        Profile.objects.create(user=cls.user, ecole=cls.ecole, role='director')

    def setUp(self):
        self.client.force_login(self.user)

    def _note(self, matiere, valeur, periode='Trimestre 1'):
        return Note.objects.create(
            ecole=self.ecole, etudiant=self.eleve, matiere=matiere,
            annee_scolaire=self.annee, periode_evaluation=periode,
            valeur=Decimal(valeur), date_evaluation=date(2026, 10, 15),
        )

    def _bulletin_url(self, periode='Trimestre 1'):
        return reverse('generer_bulletin_scolaire', args=[self.eleve.pk, periode])

    def test_decimal_average_is_rounded_once(self):
        self.assertEqual(
            moyenne_ponderee(((Decimal('10.01'), 1), (Decimal('10.02'), 2))),
            Decimal('10.02'),
        )

    def test_complete_programme_produces_weighted_rows(self):
        self._note(self.francais, '10.00')
        self._note(self.maths, '15.00')
        rows, moyenne = bulletin_trimestriel(self.inscription, 'Trimestre 1')
        self.assertEqual(
            [(row['matiere'], row['valeur'], row['coefficient']) for row in rows],
            [('Français', '10.00', 1), ('Mathématiques', '15.00', 2)],
        )
        self.assertIn('note_legacy_id', rows[0]['sources'][0])
        self.assertEqual(moyenne, '13.33')
        with patch('dashboard.views.documents._issue_archived_document', return_value=HttpResponse('ok')) as issue:
            preview = self.client.get(self._bulletin_url())
            self.assertEqual(preview.status_code, 200)
            self.assertContains(preview, '13.33')
            issue.assert_not_called()
            response = self.client.post(self._bulletin_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(issue.call_args.kwargs['moyenne'], '13.33')

    def test_missing_programme_note_blocks_issuance(self):
        self._note(self.maths, '15.00')
        with self.assertRaisesMessage(BulletinCalculationError, 'Français'):
            bulletin_trimestriel(self.inscription, 'Trimestre 1')
        response = self.client.get(self._bulletin_url())
        self.assertEqual(response.status_code, 409)
        self.assertIn('Français', response.content.decode())

    def test_non_positive_coefficient_is_rejected_by_calculation(self):
        with self.assertRaisesMessage(BulletinCalculationError, 'coefficient positif'):
            moyenne_ponderee(((Decimal('15.00'), 0),))

    def test_note_outside_class_programme_blocks_issuance(self):
        self._note(self.francais, '10.00')
        self._note(self.maths, '15.00')
        histoire = Matiere.objects.create(ecole=self.ecole, nom='Histoire')
        self._note(histoire, '12.00')
        response = self.client.get(self._bulletin_url())
        self.assertEqual(response.status_code, 409)
        self.assertIn('Histoire', response.content.decode())

    def test_annual_bulletin_is_blocked_without_validated_policy(self):
        self._note(self.francais, '10.00', 'Annuelle')
        response = self.client.get(self._bulletin_url('Annuelle'))
        self.assertEqual(response.status_code, 409)
        self.assertIn('règle de calcul', response.content.decode())
