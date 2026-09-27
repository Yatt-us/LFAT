"""Tests unitaires et d'intégration pour les fonctionnalités SaaS scolaires maliennes.

Couvre :
- Les mentions officielles maliennes et recommandations de passage
- Le calcul du classement avec gestion des ex-aequo
- La gestion des tuteurs, liens familiaux et remises fratrie
- Les modes de paiement mobile money (Orange Money, Wave, Sama Money) et reçus sécurisés
- L'automatisation en masse des bulletins de classe avec émission de PDF officiels,
  archivage, décisions du conseil de classe, notifications parents et pack ZIP.
"""

import io
import zipfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from parcours_scolaire.models import AffectationClasse
from .academic_calculations import (
    calculer_classement_classe,
    determiner_mention_malienne,
    recommander_decision_passage,
)
from .bulletin_automation import automatiser_bulletins_classe, creer_zip_bulletins_classe
from .finance import detecter_remise_fratrie, generer_recu_securise
from .models import (
    AnneeScolaire,
    Classe,
    CreanceScolaire,
    DecisionConseilClasse,
    DocumentEmis,
    EcoleSettings,
    Etudiant,
    LienTuteur,
    Matiere,
    ModeleDocument,
    Note,
    NotificationParent,
    Paiement,
    Profile,
    ProgrammeMatiere,
    Tuteur,
)


class SaasFeaturesTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(
            nom_etablissement="Complexe Scolaire Moderne de Bamako",
            commune="Commune IV",
            telephone="+223 70 00 00 01",
        )
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole,
            annee="2026-2027",
            date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30),
            active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole,
            annee_scolaire=cls.annee,
            nom_classe="9e Année A",
            niveau="9AF",
        )
        cls.maths = Matiere.objects.create(ecole=cls.ecole, nom="Mathématiques")
        cls.francais = Matiere.objects.create(ecole=cls.ecole, nom="Français")

        cls.prog_maths = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.maths, coefficient=3,
        )
        cls.prog_francais = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.francais, coefficient=2,
        )

        cls.admin_user = User.objects.create_user(username="directeur_saas", password="password123")
        Profile.objects.create(user=cls.admin_user, ecole=cls.ecole, role="director")

        ModeleDocument.objects.create(
            ecole=cls.ecole,
            type_document=ModeleDocument.TYPE_BULLETIN,
            titre="Bulletin Officiel Défaut",
            actif=True,
        )

        cls.etudiants = []
        cls.inscriptions = []

        # Élève 1 : Moussa Coulibaly
        e1 = Etudiant.objects.create(
            ecole=cls.ecole,
            nom="Coulibaly",
            prenom="Moussa",
            date_naissance=date(2011, 5, 12),
            genre="M",
            annee_scolaire_inscription=cls.annee,
            classe=cls.classe,
            contact_parent="+223 76 11 22 33",
            numero_matricule="MAT-001",
        )
        cls.etudiants.append(e1)
        insc1 = e1.inscriptions.create(
            ecole=cls.ecole,
            annee_scolaire=cls.annee,
            classe=cls.classe,
            date_inscription=date(2026, 9, 1),
            statut="active",
        )
        cls.inscriptions.append(insc1)
        AffectationClasse.objects.create(
            inscription=insc1, classe=cls.classe, date_debut=date(2026, 9, 1),
        )

        # Élève 2 : Aminata Coulibaly (sœur de Moussa)
        e2 = Etudiant.objects.create(
            ecole=cls.ecole,
            nom="Coulibaly",
            prenom="Aminata",
            date_naissance=date(2013, 8, 20),
            genre="F",
            annee_scolaire_inscription=cls.annee,
            classe=cls.classe,
            contact_parent="+223 76 11 22 33",
            numero_matricule="MAT-002",
        )
        cls.etudiants.append(e2)
        insc2 = e2.inscriptions.create(
            ecole=cls.ecole,
            annee_scolaire=cls.annee,
            classe=cls.classe,
            date_inscription=date(2026, 9, 1),
            statut="active",
        )
        cls.inscriptions.append(insc2)
        AffectationClasse.objects.create(
            inscription=insc2, classe=cls.classe, date_debut=date(2026, 9, 1),
        )

        cls.tuteur = Tuteur.objects.create(
            ecole=cls.ecole,
            nom="Coulibaly",
            prenom="Amadou",
            telephone_principal="+223 76 11 22 33",
            canal_prefere="sms",
            quartier="Lafiabougou",
        )
        LienTuteur.objects.create(
            tuteur=cls.tuteur,
            etudiant=e1,
            lien_parente="pere",
            est_responsable_financier=True,
            est_contact_urgence=True,
        )
        LienTuteur.objects.create(
            tuteur=cls.tuteur,
            etudiant=e2,
            lien_parente="pere",
            est_responsable_financier=True,
            est_contact_urgence=True,
        )

        # Notes Moussa (16 en maths coeff 3, 14 en français coeff 2) -> 15.20 (Bien)
        Note.objects.create(
            ecole=cls.ecole, etudiant=e1, matiere=cls.maths,
            annee_scolaire=cls.annee, periode_evaluation="Trimestre 1",
            valeur=Decimal("16.00"),
        )
        Note.objects.create(
            ecole=cls.ecole, etudiant=e1, matiere=cls.francais,
            annee_scolaire=cls.annee, periode_evaluation="Trimestre 1",
            valeur=Decimal("14.00"),
        )

        # Notes Aminata (11 en maths coeff 3, 12 en français coeff 2) -> 11.40 (Passable)
        Note.objects.create(
            ecole=cls.ecole, etudiant=e2, matiere=cls.maths,
            annee_scolaire=cls.annee, periode_evaluation="Trimestre 1",
            valeur=Decimal("11.00"),
        )
        Note.objects.create(
            ecole=cls.ecole, etudiant=e2, matiere=cls.francais,
            annee_scolaire=cls.annee, periode_evaluation="Trimestre 1",
            valeur=Decimal("12.00"),
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_malian_mentions_and_decisions(self):
        """Vérifie le barème officiel des mentions maliennes et les recommandations de passage."""
        self.assertEqual(determiner_mention_malienne(Decimal("16.50")), "tres_bien")
        self.assertEqual(determiner_mention_malienne(Decimal("14.00")), "bien")
        self.assertEqual(determiner_mention_malienne(Decimal("12.25")), "assez_bien")
        self.assertEqual(determiner_mention_malienne(Decimal("10.00")), "passable")
        self.assertEqual(determiner_mention_malienne(Decimal("9.50")), "avertissement")
        self.assertEqual(determiner_mention_malienne(Decimal("7.00")), "blame")

        self.assertEqual(recommander_decision_passage(Decimal("11.40")), "admis")
        self.assertEqual(recommander_decision_passage(Decimal("9.80")), "conseil")
        self.assertEqual(recommander_decision_passage(Decimal("8.50")), "redouble")

    def test_tuteurs_and_fratrie_detection(self):
        """Vérifie la détection de fratrie et les réductions tarifaires automatiques."""
        e1, e2 = self.etudiants
        fratrie_e1 = e1.fratrie()
        self.assertIn(e2, fratrie_e1)

        remise_type, remise_pct = detecter_remise_fratrie(e2)
        self.assertEqual(remise_type, "fratrie")
        self.assertEqual(remise_pct, Decimal("10.00"))

        self.assertEqual(e1.get_responsable_financier(), self.tuteur)
        self.assertEqual(e2.get_contact_urgence(), self.tuteur)

    def test_secure_mobile_money_receipt(self):
        """Vérifie les paiements mobile money (Orange Money, Wave, etc.) et le code de reçu infalsifiable."""
        e1 = self.etudiants[0]
        creance = CreanceScolaire.objects.create(
            ecole=self.ecole,
            etudiant=e1,
            annee_scolaire=self.annee,
            libelle="Frais de scolarité Octobre",
            montant_du=Decimal("25000.00"),
            remise_type="fratrie",
            remise_montant=Decimal("2500.00"),
        )
        self.assertEqual(creance.montant_net, Decimal("22500.00"))

        paiement = Paiement.objects.create(
            ecole=self.ecole,
            etudiant=e1,
            annee_scolaire=self.annee,
            montant=Decimal("22500.00"),
            date_paiement=timezone.now().date(),
            statut="paye",
            creance=creance,
            mode_paiement="orange_money",
            reference_transaction="OM-2026-BKO-9941",
            telephone_payeur="+223 76 11 22 33",
        )
        code_recu = generer_recu_securise(paiement)
        self.assertTrue(code_recu.startswith("REC-"))
        self.assertIn(str(paiement.pk), code_recu)

    def test_batch_bulletin_automation(self):
        """Vérifie la génération en masse, l'attribution des rangs, les décisions et les notifications."""
        resultats = automatiser_bulletins_classe(
            request=None,
            classe=self.classe,
            periode="Trimestre 1",
            user=self.admin_user,
            notifier_parents=True,
        )
        self.assertEqual(len(resultats["succes"]), 2)
        self.assertEqual(len(resultats["erreurs"]), 0)
        self.assertEqual(resultats["effectif"], 2)

        premier = resultats["succes"][0]
        self.assertEqual(premier["etudiant"], self.etudiants[0])
        self.assertEqual(premier["rang"], 1)
        self.assertEqual(premier["mention"], "bien")
        self.assertEqual(premier["moyenne"], "15.20")

        deuxieme = resultats["succes"][1]
        self.assertEqual(deuxieme["etudiant"], self.etudiants[1])
        self.assertEqual(deuxieme["rang"], 2)
        self.assertEqual(deuxieme["mention"], "passable")
        self.assertEqual(deuxieme["moyenne"], "11.40")

        docs = DocumentEmis.objects.filter(
            ecole=self.ecole,
            type_document=ModeleDocument.TYPE_BULLETIN,
            statut=DocumentEmis.STATUT_VALIDE,
        )
        self.assertEqual(docs.count(), 2)

        decisions = DecisionConseilClasse.objects.filter(inscription__classe=self.classe, periode="Trimestre 1")
        self.assertEqual(decisions.count(), 2)
        dec_1 = decisions.get(inscription=self.inscriptions[0])
        self.assertEqual(dec_1.rang, 1)
        self.assertEqual(dec_1.mention, "bien")

        notifs = NotificationParent.objects.filter(ecole=self.ecole, type_evenement="bulletin")
        self.assertEqual(notifs.count(), 2)
        self.assertIn("15.20/20", notifs.filter(etudiant=self.etudiants[0]).first().message)

    def test_zip_bulletins_export(self):
        """Vérifie la création du pack ZIP contenant tous les bulletins de la classe."""
        automatiser_bulletins_classe(
            request=None,
            classe=self.classe,
            periode="Trimestre 1",
            user=self.admin_user,
        )
        zip_buffer = creer_zip_bulletins_classe(self.classe, "Trimestre 1")
        self.assertIsInstance(zip_buffer, io.BytesIO)

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            fichiers = zf.namelist()
            self.assertEqual(len(fichiers), 2)
            self.assertTrue(any("Coulibaly_Moussa" in f for f in fichiers))
            self.assertTrue(any("Coulibaly_Aminata" in f for f in fichiers))

    def test_views_bulletin_automation(self):
        """Vérifie les vues GET, POST et téléchargement ZIP."""
        url_auto = reverse("automatiser_bulletins_classe", args=[self.classe.pk, "Trimestre 1"])

        resp_get = self.client.get(url_auto)
        self.assertEqual(resp_get.status_code, 200)
        self.assertTemplateUsed(resp_get, "dashboard/bulletins/automatisation_bulletins_classe.html")
        self.assertContains(resp_get, "Moussa")
        self.assertContains(resp_get, "Aminata")

        resp_post = self.client.post(url_auto, {"notifier_parents": "1"})
        self.assertRedirects(resp_post, url_auto)

        url_zip = reverse("telecharger_bulletins_zip", args=[self.classe.pk, "Trimestre 1"])
        resp_zip = self.client.get(url_zip)
        self.assertEqual(resp_zip.status_code, 200)
        self.assertEqual(resp_zip["Content-Type"], "application/zip")
        self.assertTrue(resp_zip["Content-Disposition"].startswith("attachment; filename=\"Bulletins_9e_Année_A_Trimestre_1.zip\""))
