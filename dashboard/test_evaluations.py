"""Évaluations multiples, résultats par inscription et limites d'accès enseignants."""

from datetime import date
from io import BytesIO
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .academic_calculations import BulletinCalculationError, bulletin_trimestriel
from .models import (
    AnneeScolaire, Classe, EcoleSettings, Enseignant, Etudiant, Evaluation,
    Inscription, Matiere, Note, Profile, ProgrammeMatiere, ResultatEvaluation,
)


class EvaluationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École des évaluations')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 6, 30), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee,
            nom_classe='7e A', niveau='7AP',
        )
        cls.maths = Matiere.objects.create(ecole=cls.ecole, nom='Mathématiques')
        cls.francais = Matiere.objects.create(ecole=cls.ecole, nom='Français')
        cls.teacher_user = User.objects.create_user(username='prof_eval', password='unused')
        Profile.objects.create(user=cls.teacher_user, ecole=cls.ecole, role='teacher')
        cls.teacher = Enseignant.objects.create(
            ecole=cls.ecole, user=cls.teacher_user, nom='Koné', prenom='Moussa',
        )
        cls.manager_user = User.objects.create_user(username='direction_eval', password='unused')
        Profile.objects.create(user=cls.manager_user, ecole=cls.ecole, role='director')
        cls.other_user = User.objects.create_user(username='prof_autre_eval', password='unused')
        Profile.objects.create(user=cls.other_user, ecole=cls.ecole, role='teacher')
        Enseignant.objects.create(
            ecole=cls.ecole, user=cls.other_user, nom='Diallo', prenom='Fatou',
        )
        cls.programme_maths = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.maths,
            enseignant=cls.teacher, coefficient=2,
        )
        cls.programme_francais = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.francais, coefficient=1,
        )
        cls.eleves = []
        cls.inscriptions = []
        from parcours_scolaire.models import AffectationClasse
        for prenom in ('Awa', 'Ibrahima'):
            eleve = Etudiant.objects.create(
                ecole=cls.ecole, nom='Traoré', prenom=prenom,
                date_naissance=date(2013, 3, 15), genre='F' if prenom == 'Awa' else 'M',
                annee_scolaire_inscription=cls.annee, classe=cls.classe,
            )
            cls.eleves.append(eleve)
            insc = Inscription.objects.create(
                ecole=cls.ecole, etudiant=eleve, annee_scolaire=cls.annee, classe=cls.classe,
                date_inscription=date(2026, 9, 1),
            )
            cls.inscriptions.append(insc)
            AffectationClasse.objects.create(
                inscription=insc, classe=cls.classe, date_debut=date(2026, 9, 1),
            )

    def _evaluation(self, titre, bareme, poids):
        return Evaluation.objects.create(
            ecole=self.ecole, programme=self.programme_maths,
            periode_evaluation='Trimestre 1', titre=titre,
            type_evaluation='Devoir', date_evaluation=date(2026, 10, 15),
            bareme=Decimal(bareme), poids=Decimal(poids), cree_par=self.teacher_user,
        )

    def _resultat(self, evaluation, inscription, valeur):
        return ResultatEvaluation.objects.create(
            evaluation=evaluation, inscription=inscription, valeur=Decimal(valeur),
            saisi_par=self.teacher_user,
        )

    def _note_legacy_francais(self):
        return Note.objects.create(
            ecole=self.ecole, etudiant=self.eleves[0], matiere=self.francais,
            annee_scolaire=self.annee, periode_evaluation='Trimestre 1',
            valeur=Decimal('10.00'), date_evaluation=date(2026, 10, 15),
        )

    def test_multiple_evaluations_calculate_subject_then_general_average(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        composition = self._evaluation('Composition', '20.00', '2.00')
        self._resultat(devoir, self.inscriptions[0], '8.00')
        self._resultat(composition, self.inscriptions[0], '12.00')
        Note.objects.create(
            ecole=self.ecole, etudiant=self.eleves[0], matiere=self.francais,
            annee_scolaire=self.annee, periode_evaluation='Trimestre 1',
            valeur=Decimal('10.00'), date_evaluation=date(2026, 10, 15),
        )
        rows, moyenne = bulletin_trimestriel(self.inscriptions[0], 'Trimestre 1')
        self.assertEqual(moyenne, '12.22')
        self.assertEqual([(row['matiere'], row['valeur']) for row in rows], [
            ('Français', '10.00'), ('Mathématiques', '13.33'),
        ])
        self.assertEqual(len(rows[1]['sources']), 2)

    def test_missing_result_blocks_bulletin(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        self._resultat(devoir, self.inscriptions[0], '8.00')
        self._evaluation('Devoir 2', '10.00', '1.00')
        self._note_legacy_francais()
        with self.assertRaisesMessage(BulletinCalculationError, 'Devoir 2'):
            bulletin_trimestriel(self.inscriptions[0], 'Trimestre 1')

    def test_legacy_and_new_results_cannot_mix_for_same_subject(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        self._resultat(devoir, self.inscriptions[0], '8.00')
        Note.objects.create(
            ecole=self.ecole, etudiant=self.eleves[0], matiere=self.maths,
            annee_scolaire=self.annee, periode_evaluation='Trimestre 1',
            valeur=Decimal('14.00'), date_evaluation=date(2026, 10, 15),
        )
        self._note_legacy_francais()
        with self.assertRaisesMessage(BulletinCalculationError, 'à la fois'):
            bulletin_trimestriel(self.inscriptions[0], 'Trimestre 1')

    def test_result_above_bareme_is_rejected(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        with self.assertRaises(ValidationError):
            self._resultat(devoir, self.inscriptions[0], '11.00')

    def test_teacher_can_create_and_enter_multiple_distinct_results(self):
        self.client.force_login(self.teacher_user)
        create_response = self.client.post(reverse('creer_evaluation'), {
            'programme': self.programme_maths.pk,
            'periode_evaluation': 'Trimestre 1', 'titre': 'Devoir 1',
            'type_evaluation': 'Devoir', 'date_evaluation': '2026-10-15',
            'bareme': '10.00', 'poids': '1.00',
        })
        self.assertEqual(create_response.status_code, 302)
        devoir = Evaluation.objects.get(titre='Devoir 1')
        results_url = reverse('saisir_resultats_evaluation', args=[devoir.pk])
        response = self.client.post(results_url, {
            f'note_{self.inscriptions[0].pk}': '8.00',
            f'note_{self.inscriptions[1].pk}': '7.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ResultatEvaluation.objects.filter(evaluation=devoir).count(), 2)
        second = self._evaluation('Devoir 2', '20.00', '1.00')
        response = self.client.post(reverse('saisir_resultats_evaluation', args=[second.pk]), {
            f'note_{self.inscriptions[0].pk}': '14.00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ResultatEvaluation.objects.filter(evaluation=devoir).count(), 2)
        self.assertEqual(ResultatEvaluation.objects.filter(evaluation=second).count(), 1)

    def test_teacher_can_cancel_and_replace_a_result_without_deleting_history(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        resultat = self._resultat(devoir, self.inscriptions[0], '8.00')
        self._note_legacy_francais()
        self.client.force_login(self.teacher_user)
        url = reverse('saisir_resultats_evaluation', args=[devoir.pk])
        response = self.client.post(url, {f'effacer_{self.inscriptions[0].pk}': 'on'})
        self.assertEqual(response.status_code, 302)
        resultat.refresh_from_db()
        self.assertTrue(resultat.annule)
        self.assertEqual(resultat.valeur, Decimal('8.00'))
        self.assertEqual(resultat.annule_par, self.teacher_user)
        with self.assertRaisesMessage(BulletinCalculationError, 'Devoir 1'):
            bulletin_trimestriel(self.inscriptions[0], 'Trimestre 1')
        response = self.client.post(url, {f'note_{self.inscriptions[0].pk}': '9.00'})
        self.assertEqual(response.status_code, 302)
        resultat.refresh_from_db()
        self.assertFalse(resultat.annule)
        self.assertEqual(resultat.valeur, Decimal('9.00'))
        self.assertEqual(ResultatEvaluation.objects.filter(evaluation=devoir).count(), 1)

    def test_creation_of_evaluation_rejects_legacy_notes_in_same_class_period(self):
        Note.objects.create(
            ecole=self.ecole, etudiant=self.eleves[0], matiere=self.maths,
            annee_scolaire=self.annee, periode_evaluation='Trimestre 1',
            valeur=Decimal('14.00'), date_evaluation=date(2026, 10, 15),
        )
        self.client.force_login(self.teacher_user)
        response = self.client.post(reverse('creer_evaluation'), {
            'programme': self.programme_maths.pk,
            'periode_evaluation': 'Trimestre 1', 'titre': 'Devoir en conflit',
            'type_evaluation': 'Devoir', 'date_evaluation': '2026-10-15',
            'bareme': '20.00', 'poids': '1.00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'notes anciennes')
        self.assertFalse(Evaluation.objects.filter(titre='Devoir en conflit').exists())

    def test_legacy_single_and_bulk_entry_reject_existing_evaluation(self):
        self._evaluation('Devoir 1', '20.00', '1.00')
        self.client.force_login(self.teacher_user)
        single = self.client.post(reverse('ajouter_note', args=[self.eleves[0].pk]), {
            'matiere': self.maths.pk, 'valeur': '14.00',
            'periode_evaluation': 'Trimestre 1', 'type_evaluation': 'Composition',
            'date_evaluation': '2026-10-15', 'annee_scolaire': self.annee.pk,
        })
        self.assertEqual(single.status_code, 200)
        self.assertContains(single, 'évaluations détaillées')
        bulk = self.client.post(reverse('saisir_notes_classe_matiere', args=[self.classe.pk, self.maths.pk]), {
            'periode_evaluation': 'Trimestre 1', 'type_evaluation': 'Composition',
            'date_evaluation': '2026-10-15', f'note_{self.eleves[0].pk}': '14.00',
        })
        self.assertEqual(bulk.status_code, 409)
        self.assertFalse(Note.objects.filter(matiere=self.maths).exists())

    def test_excel_import_rejects_existing_evaluation(self):
        self._evaluation('Devoir 1', '20.00', '1.00')
        Etudiant.objects.filter(pk=self.eleves[0].pk).update(numero_matricule='TEST-EVAL-001')
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['MATRICULE', 'NOM', 'PRENOM', 'CLASSE', 'MATIERE', 'NOTE', 'PERIODE', 'ANNEE_SCOLAIRE'])
        sheet.append(['TEST-EVAL-001', 'Traoré', 'Awa', self.classe.nom_classe, self.maths.nom, 14, 'Trimestre 1', self.annee.annee])
        data = BytesIO()
        workbook.save(data)
        self.client.force_login(self.manager_user)
        form_page = self.client.get(reverse('import_notes_excel'))
        self.assertContains(form_page, 'enctype="multipart/form-data"')
        self.assertNotContains(form_page, 'preventDefault')
        response = self.client.post(reverse('import_notes_excel'), {
            'file': SimpleUploadedFile('notes.xlsx', data.getvalue()),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Note.objects.filter(matiere=self.maths).exists())
        self.assertContains(response, 'Import annulé')

    def test_direct_annual_note_is_rejected_and_absent_from_form(self):
        self.client.force_login(self.teacher_user)
        url = reverse('ajouter_note', args=[self.eleves[0].pk])
        form_page = self.client.get(url)
        self.assertEqual(form_page.status_code, 200)
        self.assertNotContains(form_page, '<option value="Annuelle"')
        response = self.client.post(url, {
            'matiere': self.maths.pk, 'valeur': '14.00',
            'periode_evaluation': 'Annuelle', 'type_evaluation': 'Composition',
            'date_evaluation': '2026-10-15', 'annee_scolaire': self.annee.pk,
        })
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'règle validée', status_code=409)
        self.assertFalse(Note.objects.filter(periode_evaluation='Annuelle').exists())

    def test_bulk_annual_note_is_rejected_and_absent_from_form(self):
        self.client.force_login(self.teacher_user)
        url = reverse('saisir_notes_classe_matiere', args=[self.classe.pk, self.maths.pk])
        form_page = self.client.get(url)
        self.assertEqual(form_page.status_code, 200)
        self.assertNotContains(form_page, '<option value="Annuelle"')
        response = self.client.post(url, {
            'periode_evaluation': 'Annuelle', 'type_evaluation': 'Composition',
            'date_evaluation': '2026-10-15', f'note_{self.eleves[0].pk}': '14.00',
        })
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'règle validée', status_code=409)
        self.assertFalse(Note.objects.filter(periode_evaluation='Annuelle').exists())

    def test_excel_import_rejects_annual_row_without_importing_other_rows(self):
        Etudiant.objects.filter(pk=self.eleves[0].pk).update(numero_matricule='TEST-ANNUEL-001')
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['MATRICULE', 'NOM', 'PRENOM', 'CLASSE', 'MATIERE', 'NOTE', 'PERIODE', 'ANNEE_SCOLAIRE'])
        for periode in ('Trimestre 1', 'Annuelle'):
            sheet.append([
                'TEST-ANNUEL-001', 'Traoré', 'Awa', self.classe.nom_classe,
                self.maths.nom, 14, periode, self.annee.annee,
            ])
        data = BytesIO()
        workbook.save(data)
        self.client.force_login(self.manager_user)
        response = self.client.post(reverse('import_notes_excel'), {
            'file': SimpleUploadedFile('notes.xlsx', data.getvalue()),
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'règle validée')
        self.assertFalse(Note.objects.filter(matiere=self.maths).exists())

    def test_historical_annual_note_is_read_only_in_school_views(self):
        note = Note.objects.create(
            ecole=self.ecole, etudiant=self.eleves[0], matiere=self.maths,
            annee_scolaire=self.annee, periode_evaluation='Annuelle',
            valeur=Decimal('14.00'), date_evaluation=date(2026, 10, 15),
        )
        self.client.force_login(self.manager_user)
        listing = self.client.get(reverse('liste_notes_par_classe_matiere'), {
            'classe_id': self.classe.pk, 'matiere_id': self.maths.pk,
        })
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Historique en lecture seule')
        for route in ('modifier_note', 'supprimer_note'):
            url = reverse(route, args=[note.pk])
            self.assertContains(self.client.get(url), 'lecture seule', status_code=409)
            self.assertContains(self.client.post(url, {
                'valeur': '19.00', 'date_evaluation': '2026-10-16',
            }), 'lecture seule', status_code=409)
        note.refresh_from_db()
        self.assertEqual(note.valeur, Decimal('14.00'))

    def test_school_cannot_delete_programme_subject_or_class_with_history(self):
        self._evaluation('Devoir 1', '10.00', '1.00')
        self._note_legacy_francais()
        self.client.force_login(self.manager_user)
        for route, pk, model in (
            ('supprimer_programme_matiere', self.programme_maths.pk, ProgrammeMatiere),
            ('supprimer_matiere', self.maths.pk, Matiere),
            ('supprimer_classe', self.classe.pk, Classe),
            ('supprimer_matiere', self.francais.pk, Matiere),
        ):
            response = self.client.post(reverse(route, args=[pk]), follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(model.objects.filter(pk=pk).exists())
            self.assertContains(response, 'alert-error')

    def test_unassigned_teacher_cannot_access_other_programme(self):
        devoir = self._evaluation('Devoir 1', '10.00', '1.00')
        self.client.force_login(self.other_user)
        response = self.client.get(reverse('saisir_resultats_evaluation', args=[devoir.pk]))
        self.assertEqual(response.status_code, 403)
        listing = self.client.get(reverse('liste_evaluations'))
        self.assertEqual(listing.status_code, 200)
        self.assertNotContains(listing, 'Devoir 1')
