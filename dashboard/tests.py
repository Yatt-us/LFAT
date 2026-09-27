"""Checks for school document layouts and their tenant boundary."""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .document_templates import render_document_html, render_document_text, validate_document_text


class DocumentTemplateTextTests(SimpleTestCase):
    def test_only_allowed_variables_are_substituted(self):
        result = render_document_text(
            "Élève : {{ eleve_nom_complet }} — {{ annee_scolaire }}",
            {"eleve_nom_complet": "Awa Traoré", "annee_scolaire": "2026-2027"},
        )
        self.assertEqual(result, "Élève : Awa Traoré — 2026-2027")

    def test_unknown_variable_and_template_logic_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_document_text("{{ secret }}")
        with self.assertRaises(ValidationError):
            validate_document_text("{% include 'private.html' %}")
        with self.assertRaises(ValidationError):
            validate_document_text("<script>alert(1)</script>")

    def test_preview_escapes_values_and_keeps_line_breaks(self):
        preview = str(render_document_html(
            "Élève : {{ eleve_nom_complet }}\nAnnée : {{ annee_scolaire }}",
            {"eleve_nom_complet": "<b>Awa</b>", "annee_scolaire": "2026-2027"},
        ))
        self.assertIn("&lt;b&gt;Awa&lt;/b&gt;", preview)
        self.assertNotIn("<b>Awa</b>", preview)
        self.assertIn("<br>", preview)

from django.test import TestCase

from .models import EcoleSettings, ModeleDocument


class SchoolDocumentTemplateTests(TestCase):
    def setUp(self):
        self.ecole_a = EcoleSettings.objects.create(nom_etablissement='École A')
        self.ecole_b = EcoleSettings.objects.create(nom_etablissement='École B')

    def test_default_is_not_saved_until_school_customizes_it(self):
        modele = ModeleDocument.pour_ecole(self.ecole_a, ModeleDocument.TYPE_FREQUENTATION)
        self.assertIsNone(modele.pk)
        self.assertEqual(ModeleDocument.objects.count(), 0)
        modele.titre = 'CERTIFICAT PROPRE À A'
        modele.save()
        self.assertEqual(
            ModeleDocument.pour_ecole(self.ecole_a, ModeleDocument.TYPE_FREQUENTATION).titre,
            'CERTIFICAT PROPRE À A',
        )
        self.assertNotEqual(
            ModeleDocument.pour_ecole(self.ecole_b, ModeleDocument.TYPE_FREQUENTATION).titre,
            'CERTIFICAT PROPRE À A',
        )
        self.assertEqual(ModeleDocument.objects.count(), 1)

    def test_multiple_custom_layouts_belong_to_one_school(self):
        for code, titre in (('attestation-sport', 'Sport'), ('lettre-de-stage', 'Stage')):
            modele = ModeleDocument.pour_ecole(self.ecole_a, ModeleDocument.TYPE_AUTRE, code=code)
            modele.titre = titre
            modele.save()
        self.assertEqual(
            list(ModeleDocument.objects.filter(ecole=self.ecole_a, type_document=ModeleDocument.TYPE_AUTRE)
                 .order_by('code').values_list('code', flat=True)),
            ['attestation-sport', 'lettre-de-stage'],
        )
        self.assertFalse(ModeleDocument.objects.filter(ecole=self.ecole_b).exists())

    def test_custom_layout_requires_code(self):
        modele = ModeleDocument(ecole=self.ecole_a, type_document=ModeleDocument.TYPE_AUTRE, titre='Libre')
        with self.assertRaises(ValidationError):
            modele.save()


class DocumentIssuanceFlowTests(TestCase):
    """The saved plan, private PDF and tenant boundary work together."""

    @classmethod
    def setUpTestData(cls):
        from datetime import date
        from django.contrib.auth import get_user_model
        from .models import AnneeScolaire, Classe, Etudiant, Inscription, Profile

        cls.ecole_a = EcoleSettings.objects.create(nom_etablissement='École de test A')
        cls.ecole_b = EcoleSettings.objects.create(nom_etablissement='École de test B')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole_a, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole_a, annee_scolaire=cls.annee,
            nom_classe='6e A', niveau='6AP',
        )
        cls.etudiant = Etudiant.objects.create(
            ecole=cls.ecole_a, nom='Traoré', prenom='Awa',
            date_naissance=date(2013, 3, 15), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        Inscription.objects.create(
            ecole=cls.ecole_a, etudiant=cls.etudiant,
            annee_scolaire=cls.annee, classe=cls.classe,
        )
        User = get_user_model()
        cls.user_a = User.objects.create_user(username='documents_a', password='unused')
        cls.user_b = User.objects.create_user(username='documents_b', password='unused')
        Profile.objects.create(user=cls.user_a, ecole=cls.ecole_a, role='school_admin')
        Profile.objects.create(user=cls.user_b, ecole=cls.ecole_b, role='school_admin')

    def setUp(self):
        import tempfile
        from unittest.mock import patch
        from .private_media import private_media_storage

        self.pdf_dir = tempfile.TemporaryDirectory(prefix='lfat-issued-test-')
        self.addCleanup(self.pdf_dir.cleanup)
        storage_patch = patch.dict(private_media_storage.__dict__, {'location': self.pdf_dir.name})
        storage_patch.start()
        self.addCleanup(storage_patch.stop)
        self.client.force_login(self.user_a)

    def test_issuance_keeps_old_plan_and_pdf_when_school_edits_layout(self):
        from django.urls import reverse
        from .models import DocumentEmis

        url = reverse('generer_attestation_scolarite', args=[self.etudiant.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        first = self.client.post(url)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.content.startswith(b'%PDF'))
        self.assertEqual(DocumentEmis.objects.count(), 1)
        archived = DocumentEmis.objects.get()
        original_title = archived.modele_snapshot['titre']
        original_bytes = archived.fichier_pdf.read()
        self.assertTrue(archived.fichier_pdf.storage.exists(archived.fichier_pdf.name))

        repeated = self.client.post(url)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(DocumentEmis.objects.count(), 1)
        self.assertEqual(b''.join(repeated.streaming_content), original_bytes)

        plan = ModeleDocument.pour_ecole(self.ecole_a, ModeleDocument.TYPE_ATTESTATION)
        plan.titre = 'ATTESTATION ADAPTÉE'
        plan.save()
        updated = self.client.post(url)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(DocumentEmis.objects.count(), 2)
        archived.refresh_from_db()
        self.assertEqual(archived.modele_snapshot['titre'], original_title)
        self.assertEqual(archived.fichier_pdf.read(), original_bytes)
        self.assertEqual(
            DocumentEmis.objects.order_by('-date_emission').first().modele_snapshot['titre'],
            'ATTESTATION ADAPTÉE',
        )

    def test_download_and_issuance_are_limited_to_the_school(self):
        from django.test import Client
        from django.urls import reverse
        from .models import DocumentEmis

        url = reverse('generer_certificat_inscription', args=[self.etudiant.pk])
        self.assertEqual(self.client.post(url).status_code, 200)
        archived = DocumentEmis.objects.get()
        download = reverse('issued_document_file', args=[archived.pk])
        self.assertEqual(self.client.get(download).status_code, 200)
        other_school = Client()
        other_school.force_login(self.user_b)
        self.assertEqual(other_school.post(url).status_code, 404)
        self.assertEqual(other_school.get(download).status_code, 404)
        verification = Client().get(reverse('verifier_document', args=[archived.code_verification]))
        self.assertEqual(verification.status_code, 200)
        self.assertContains(verification, archived.numero_document)
        self.assertNotContains(verification, self.etudiant.nom)
