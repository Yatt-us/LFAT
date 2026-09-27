"""Contrôles ciblés de l'historique de classe et de sa reprise."""

from datetime import date
from importlib import import_module
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from dashboard.models import AnneeScolaire, Classe, EcoleSettings, Etudiant, Inscription, Profile
from .models import AffectationClasse
from .services import synchroniser_affectation


class AffectationClasseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École historique')
        cls.autre_ecole = EcoleSettings.objects.create(nom_etablissement='Autre école')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 7, 1), active=True,
        )
        cls.annee_etrangere = AnneeScolaire.objects.create(
            ecole=cls.autre_ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 7, 1), active=True,
        )
        cls.classe_a = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee, nom_classe='7e A', niveau='7AP',
        )
        cls.classe_b = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee, nom_classe='7e B', niveau='7AP',
        )
        cls.classe_etrangere = Classe.objects.create(
            ecole=cls.autre_ecole, annee_scolaire=cls.annee_etrangere,
            nom_classe='7e autre', niveau='7AP',
        )
        cls.etudiant = Etudiant.objects.create(
            ecole=cls.ecole, nom='Traoré', prenom='Aminata',
            date_naissance=date(2012, 5, 1), genre='F',
            annee_scolaire_inscription=cls.annee, classe=cls.classe_a,
        )
        cls.inscription = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.etudiant, annee_scolaire=cls.annee,
            classe=cls.classe_a, date_inscription=date(2026, 9, 1), statut='active',
        )
        AffectationClasse.objects.create(
            inscription=cls.inscription, classe=cls.classe_a,
            date_debut=date(2026, 9, 1),
        )
        cls.user = get_user_model().objects.create_user(
            username='historique_admin', password='unused',
        )
        Profile.objects.create(user=cls.user, ecole=cls.ecole, role='school_admin')

    def test_intervalles_ouverts_chevauchements_et_ecole_sont_controles(self):
        with self.assertRaises(ValidationError):
            AffectationClasse.objects.create(
                inscription=self.inscription, classe=self.classe_b,
                date_debut=date(2026, 9, 15),
            )
        with self.assertRaises(ValidationError):
            AffectationClasse.objects.create(
                inscription=self.inscription, classe=self.classe_etrangere,
                date_debut=date(2026, 9, 15),
            )
        with self.assertRaises(ValidationError):
            AffectationClasse.objects.create(
                inscription=self.inscription, classe=self.classe_b,
                date_debut=date(2026, 8, 31),
            )

    def test_transfert_puis_suspension_ferment_les_intervalles(self):
        self.inscription.classe = self.classe_b
        self.inscription.save(update_fields=['classe'])
        synchroniser_affectation(self.inscription, date_effet=date(2026, 9, 20))
        self.inscription.statut = 'suspendue'
        self.inscription.save(update_fields=['statut'])
        synchroniser_affectation(self.inscription, date_effet=date(2026, 9, 25))
        self.assertEqual(list(AffectationClasse.objects.filter(
            inscription=self.inscription,
        ).order_by('date_debut').values_list('classe_id', 'date_debut', 'date_fin')), [
            (self.classe_a.pk, date(2026, 9, 1), date(2026, 9, 20)),
            (self.classe_b.pk, date(2026, 9, 20), date(2026, 9, 25)),
        ])
        self.assertFalse(AffectationClasse.objects.filter(
            inscription=self.inscription, date_fin__isnull=True,
        ).exists())

    def test_correction_le_meme_jour_retablit_un_seul_intervalle(self):
        self.inscription.classe = self.classe_b
        self.inscription.save(update_fields=['classe'])
        synchroniser_affectation(self.inscription, date_effet=date(2026, 9, 20))
        self.inscription.classe = self.classe_a
        self.inscription.save(update_fields=['classe'])
        synchroniser_affectation(self.inscription, date_effet=date(2026, 9, 20))
        self.assertEqual(list(AffectationClasse.objects.filter(
            inscription=self.inscription,
        ).values_list('classe_id', 'date_debut', 'date_fin')), [
            (self.classe_a.pk, date(2026, 9, 1), None),
        ])

    def test_flux_inscription_et_fiche_affichent_un_transfert_date(self):
        self.client.force_login(self.user)
        url = reverse('inscrire_etudiant', args=[self.etudiant.pk])
        with patch('dashboard.views.students.timezone.localdate', return_value=date(2026, 9, 20)):
            reponse = self.client.post(url, {'classe': self.classe_b.pk, 'statut': 'active'})
        self.assertRedirects(reponse, reverse('detail_etudiant', args=[self.etudiant.pk]))
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.classe_id, self.classe_b.pk)
        historique = list(AffectationClasse.objects.filter(
            inscription=self.inscription,
        ).order_by('date_debut').values_list('classe_id', 'date_debut', 'date_fin'))
        self.assertEqual(historique, [
            (self.classe_a.pk, date(2026, 9, 1), date(2026, 9, 20)),
            (self.classe_b.pk, date(2026, 9, 20), None),
        ])
        lignes = list(AffectationClasse.objects.filter(
            inscription=self.inscription,
        ).order_by('date_debut'))
        self.assertEqual(lignes[0].termine_par_id, self.user.pk)
        self.assertEqual(lignes[1].cree_par_id, self.user.pk)
        fiche = self.client.get(reverse('detail_etudiant', args=[self.etudiant.pk]))
        self.assertContains(fiche, 'Historique des classes')
        self.assertContains(fiche, '7e A')
        self.assertContains(fiche, '7e B')
        self.assertContains(
            fiche, reverse('creer_certificat_interface') + f'?etudiant_id={self.etudiant.pk}',
        )
        for periode in ('Trimestre 1', 'Trimestre 2', 'Trimestre 3', 'Annuelle'):
            self.assertContains(fiche, reverse('generer_bulletin_scolaire', args=[self.etudiant.pk, periode]))


    def test_preinscription_future_et_correction_avant_effet(self):
        annee_future = AnneeScolaire.objects.create(
            ecole=self.ecole, annee='2027-2028', date_debut=date(2027, 9, 1),
            date_fin=date(2028, 7, 1), active=True,
        )
        classe_future_a = Classe.objects.create(
            ecole=self.ecole, annee_scolaire=annee_future,
            nom_classe='8e A', niveau='8AP',
        )
        classe_future_b = Classe.objects.create(
            ecole=self.ecole, annee_scolaire=annee_future,
            nom_classe='8e B', niveau='8AP',
        )
        inscription_future = Inscription.objects.create(
            ecole=self.ecole, etudiant=self.etudiant, annee_scolaire=annee_future,
            classe=classe_future_a, date_inscription=date(2026, 9, 27), statut='active',
        )
        affectation = synchroniser_affectation(
            inscription_future, date_effet=date(2026, 9, 27), acteur=self.user,
        )
        self.assertEqual(affectation.date_debut, date(2027, 9, 1))
        self.assertEqual(affectation.cree_par_id, self.user.pk)
        inscription_future.classe = classe_future_b
        inscription_future.save(update_fields=['classe'])
        correction = synchroniser_affectation(
            inscription_future, date_effet=date(2026, 9, 27), acteur=self.user,
        )
        self.assertEqual(correction.pk, affectation.pk)
        self.assertEqual(correction.classe_id, classe_future_b.pk)
        self.assertEqual(AffectationClasse.objects.filter(inscription=inscription_future).count(), 1)


class RepriseAffectationsTests(TestCase):
    def test_reprise_prudente_du_pointeur_actuel(self):
        ecole = EcoleSettings.objects.create(nom_etablissement='École de reprise')
        annee = AnneeScolaire.objects.create(
            ecole=ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 7, 1), active=True,
        )
        classe = Classe.objects.create(
            ecole=ecole, annee_scolaire=annee, nom_classe='8e A', niveau='8AP',
        )
        eleve = Etudiant.objects.create(
            ecole=ecole, nom='Koné', prenom='Fatou', date_naissance=date(2011, 1, 1),
            genre='F', annee_scolaire_inscription=annee, classe=classe,
        )
        inscription = Inscription.objects.create(
            ecole=ecole, etudiant=eleve, annee_scolaire=annee, classe=classe,
            date_inscription=date(2026, 8, 20), statut='active',
        )
        autre_ecole = EcoleSettings.objects.create(nom_etablissement='Autre reprise')
        autre_annee = AnneeScolaire.objects.create(
            ecole=autre_ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 7, 1), active=True,
        )
        classe_etrangere = Classe.objects.create(
            ecole=autre_ecole, annee_scolaire=autre_annee,
            nom_classe='8e étrangère', niveau='8AP',
        )
        autre_eleve = Etudiant.objects.create(
            ecole=ecole, nom='Diarra', prenom='Mariam', date_naissance=date(2011, 2, 1),
            genre='F', annee_scolaire_inscription=annee,
        )
        inscription_incoherente = Inscription.objects.create(
            ecole=ecole, etudiant=autre_eleve, annee_scolaire=annee,
            classe=classe_etrangere, date_inscription=date(2026, 9, 1), statut='active',
        )
        class Editeur:
            connection = connection
        migration = import_module('parcours_scolaire.migrations.0001_initial')
        with patch.object(migration.timezone, 'localdate', return_value=date(2026, 9, 20)):
            migration.reprendre_affectations_courantes(apps, Editeur())
        affectation = AffectationClasse.objects.get(inscription=inscription)
        self.assertEqual(affectation.classe_id, classe.pk)
        self.assertEqual(affectation.date_debut, date(2026, 9, 20))
        self.assertEqual(affectation.origine, AffectationClasse.Origine.REPRISE)
        self.assertFalse(AffectationClasse.objects.filter(
            inscription=inscription_incoherente,
        ).exists())
        inscription.classe = None
        inscription.save(update_fields=['classe'])
        sortie = StringIO()
        call_command('auditer_affectations', ecole=ecole.pk, stdout=sortie)
        self.assertIn(f'inscription={inscription.pk}', sortie.getvalue())
        self.assertIn('inscription_active_sans_classe', sortie.getvalue())
        self.assertIn('affectation_ouverte_sans_classe', sortie.getvalue())
        self.assertIn(f'inscription={inscription_incoherente.pk}', sortie.getvalue())
        self.assertIn('classe_autre_ecole', sortie.getvalue())
