"""Les certificats sont émis explicitement avec l'identité de leur école."""

from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import (
    AnneeScolaire, CertificatFrequentation, Classe, EcoleSettings,
    Etudiant, Inscription, Profile,
)
from .private_media import private_media_storage


class CertificatIdentiteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(
            nom_etablissement='École du Fleuve',
            ministere='Ministère de l’Éducation Nationale',
            academie='Académie locale',
            adresse_etablissement='Bamako',
        )
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027',
            date_debut=date(2026, 9, 1), date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee,
            nom_classe='7e A', niveau='7AP',
        )
        cls.eleve = Etudiant.objects.create(
            ecole=cls.ecole, nom='Exemple', prenom='Certificat',
            date_naissance=date(2012, 1, 1), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve,
            annee_scolaire=cls.annee, classe=cls.classe,
        )
        cls.directeur = User.objects.create_user(username='directeur_certificat', password='unused')
        Profile.objects.create(user=cls.directeur, ecole=cls.ecole, role='director')

    def setUp(self):
        self.client.force_login(self.directeur)
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        storage_patch = patch.object(private_media_storage, 'location', temp.name)
        storage_patch.start()
        self.addCleanup(storage_patch.stop)

    def test_direct_get_redirects_to_form_without_issuing(self):
        response = self.client.get(reverse('generer_certificat_frequentation', args=[self.eleve.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('etudiant_id=', response['Location'])
        self.assertFalse(CertificatFrequentation.objects.exists())

    @patch('dashboard.views.documents._render_configured_pdf', return_value=b'%PDF-1.4 certificat-test')
    def test_post_issues_certificate_with_school_identity(self, _render):
        response = self.client.post(reverse('creer_certificat_interface'), {
            'etudiant': self.eleve.pk,
            'date_delivrance': '2026-10-01',
            'lieu_delivrance': 'Bamako',
            'mention_legale': 'Élève inscrit',
            'remarque': '',
        })
        self.assertEqual(response.status_code, 200)
        certificat = CertificatFrequentation.objects.get()
        self.assertEqual(certificat.ministere, self.ecole.ministere)
        self.assertEqual(certificat.academie, self.ecole.academie)
        self.assertEqual(certificat.etablissement_reference, self.ecole.nom_etablissement)
        self.assertEqual(certificat.adresse_etablissement, self.ecole.adresse_etablissement)
        self.assertNotIn('Banankabougou', certificat.etablissement_reference)
