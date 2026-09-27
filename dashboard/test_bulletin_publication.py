"""La consultation d'un bulletin ne publie rien ; chaque version publiée est traçable."""

from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    AnneeScolaire, Classe, DocumentEmis, EcoleSettings, Etudiant, Inscription,
    Matiere, Note, Profile, ProgrammeMatiere,
)
from .private_media import private_media_storage


class BulletinPublicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École de démonstration')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee, nom_classe='6e A', niveau='6AP',
        )
        cls.eleve = Etudiant.objects.create(
            ecole=cls.ecole, nom='Exemple', prenom='Élève',
            date_naissance=date(2013, 1, 1), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        cls.inscription = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve,
            annee_scolaire=cls.annee, classe=cls.classe,
        )
        cls.matiere = Matiere.objects.create(ecole=cls.ecole, nom='Français')
        ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.matiere, coefficient=2,
        )
        cls.note = Note.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve, matiere=cls.matiere,
            annee_scolaire=cls.annee, periode_evaluation='Trimestre 1',
            valeur=Decimal('12.00'), date_evaluation=date(2026, 10, 1),
        )
        cls.directeur = User.objects.create_user(username='directeur_publication', password='unused')
        Profile.objects.create(user=cls.directeur, ecole=cls.ecole, role='director')

    def setUp(self):
        self.client.force_login(self.directeur)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        storage_patch = patch.object(private_media_storage, 'location', temp.name)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.url = reverse('generer_bulletin_scolaire', args=[self.eleve.pk, 'Trimestre 1'])

    def test_get_previews_without_issuing_document(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '12.00')
        self.assertContains(response, 'Publier et télécharger')
        self.assertFalse(DocumentEmis.objects.exists())

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 publication-test')
    def test_new_publication_revokes_previous_version_for_same_period(self, _render):
        first = self.client.post(self.url)
        self.assertEqual(first.status_code, 200)
        old = DocumentEmis.objects.get()
        self.assertEqual(old.statut, DocumentEmis.STATUT_VALIDE)
        self.assertEqual(old.donnees_snapshot['moyenne'], '12.00')

        Note.objects.filter(pk=self.note.pk).update(valeur=Decimal('16.00'))
        second = self.client.post(self.url)
        self.assertEqual(second.status_code, 200)
        old.refresh_from_db()
        self.assertEqual(old.statut, DocumentEmis.STATUT_ANNULE)
        self.assertIsNotNone(old.annule_le)
        self.assertEqual(old.annule_par, self.directeur)
        self.assertIn('Remplacé', old.motif_annulation)
        current = DocumentEmis.objects.get(statut=DocumentEmis.STATUT_VALIDE)
        self.assertEqual(current.donnees_snapshot['moyenne'], '16.00')
        self.assertNotEqual(old.code_verification, current.code_verification)
        self.assertEqual(DocumentEmis.objects.count(), 2)
        self.assertEqual(
            self.client.get(reverse('verifier_document', args=[old.code_verification])).status_code,
            200,
        )

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 publication-test')
    def test_identical_republication_reuses_current_document(self, _render):
        self.client.post(self.url)
        self.client.post(self.url)
        self.assertEqual(DocumentEmis.objects.count(), 1)

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 publication-test')
    def test_manual_revocation_requires_post_and_reason(self, _render):
        self.client.post(self.url)
        document = DocumentEmis.objects.get()
        revoke_url = reverse('annuler_document_emis', args=[document.pk])
        self.assertEqual(self.client.get(revoke_url).status_code, 405)
        self.assertEqual(self.client.post(revoke_url, {'motif': ''}).status_code, 400)
        document.refresh_from_db()
        self.assertEqual(document.statut, DocumentEmis.STATUT_VALIDE)

        response = self.client.post(revoke_url, {'motif': 'Correction de la note publiée'})
        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertEqual(document.statut, DocumentEmis.STATUT_ANNULE)
        self.assertEqual(document.annule_par, self.directeur)
        self.assertEqual(document.motif_annulation, 'Correction de la note publiée')
        verification = self.client.get(reverse('verifier_document', args=[document.code_verification]))
        self.assertContains(verification, 'Document annulé')

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 publication-test')
    def test_other_school_cannot_revoke_document(self, _render):
        self.client.post(self.url)
        document = DocumentEmis.objects.get()
        autre_ecole = EcoleSettings.objects.create(nom_etablissement='Autre école')
        autre = User.objects.create_user(username='autre_directeur_publication', password='unused')
        Profile.objects.create(user=autre, ecole=autre_ecole, role='director')
        self.client.force_login(autre)
        response = self.client.post(
            reverse('annuler_document_emis', args=[document.pk]),
            {'motif': 'Motif sans autorisation'},
        )
        self.assertEqual(response.status_code, 404)
        document.refresh_from_db()
        self.assertEqual(document.statut, DocumentEmis.STATUT_VALIDE)
