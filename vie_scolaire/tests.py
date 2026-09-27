from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from dashboard.models import (
    AnneeScolaire, Classe, EcoleSettings, Enseignant, Etudiant, Inscription,
    Matiere, Profile, ProgrammeMatiere,
)
from parcours_scolaire.models import AffectationClasse
from parcours_scolaire.services import synchroniser_affectation
from .models import Justification, Pointage, Seance


class ParcoursSeanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ecole = EcoleSettings.objects.create(nom_etablissement='École A')
        cls.autre_ecole = EcoleSettings.objects.create(nom_etablissement='École B')
        cls.annee = AnneeScolaire.objects.create(
            ecole=cls.ecole, annee='2026-2027', date_debut=date(2026, 9, 1),
            date_fin=date(2027, 7, 1), active=True,
        )
        cls.classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee, nom_classe='6e A', niveau='6AP',
        )
        cls.autre_classe = Classe.objects.create(
            ecole=cls.ecole, annee_scolaire=cls.annee, nom_classe='6e B', niveau='6AP',
        )
        cls.admin = get_user_model().objects.create_user(username='vs_admin', password='unused')
        cls.direction = get_user_model().objects.create_user(username='vs_direction', password='unused')
        cls.prof_user = get_user_model().objects.create_user(username='vs_prof', password='unused')
        cls.autre_user = get_user_model().objects.create_user(username='vs_autre', password='unused')
        Profile.objects.create(user=cls.admin, ecole=cls.ecole, role='school_admin')
        Profile.objects.create(user=cls.direction, ecole=cls.ecole, role='director')
        Profile.objects.create(user=cls.prof_user, ecole=cls.ecole, role='teacher')
        Profile.objects.create(user=cls.autre_user, ecole=cls.autre_ecole, role='school_admin')
        cls.prof = Enseignant.objects.create(
            ecole=cls.ecole, nom='Diallo', prenom='Moussa', user=cls.prof_user,
        )
        cls.matiere = Matiere.objects.create(ecole=cls.ecole, nom='Mathématiques')
        cls.programme = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.classe, matiere=cls.matiere,
            enseignant=cls.prof, coefficient=2,
        )
        cls.autre_programme = ProgrammeMatiere.objects.create(
            ecole=cls.ecole, classe=cls.autre_classe, matiere=cls.matiere,
            enseignant=cls.prof, coefficient=2,
        )
        cls.eleve_a = Etudiant.objects.create(
            ecole=cls.ecole, nom='Diallo', prenom='Awa', date_naissance=date(2012, 2, 1),
            genre='F', annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        cls.eleve_b = Etudiant.objects.create(
            ecole=cls.ecole, nom='Traoré', prenom='Bakary', date_naissance=date(2012, 4, 1),
            genre='M', annee_scolaire_inscription=cls.annee, classe=cls.classe,
        )
        cls.inscription_a = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve_a, annee_scolaire=cls.annee,
            classe=cls.classe, date_inscription=date(2026, 9, 1), statut='active',
        )
        cls.inscription_b = Inscription.objects.create(
            ecole=cls.ecole, etudiant=cls.eleve_b, annee_scolaire=cls.annee,
            classe=cls.classe, date_inscription=date(2026, 9, 1), statut='active',
        )
        for inscription in (cls.inscription_a, cls.inscription_b):
            AffectationClasse.objects.create(
                inscription=inscription, classe=cls.classe, date_debut=date(2026, 9, 1),
            )

    def setUp(self):
        self.client.force_login(self.admin)

    def creer(self):
        return Seance.objects.create(
            ecole=self.ecole, classe=self.classe, programme=self.programme,
            enseignant=self.prof, date=date(2026, 9, 28),
            heure_debut=time(8, 0), heure_fin=time(9, 0), cree_par=self.admin,
        )

    def donnees_pointage(self, statut_a='', statut_b='', minutes_b=''):
        return {
            'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '2',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '2',
            'form-0-inscription': str(self.inscription_a.pk), 'form-0-statut': statut_a,
            'form-1-inscription': str(self.inscription_b.pk), 'form-1-statut': statut_b,
            'form-1-minutes_retard': minutes_b,
        }

    def test_creation_et_pointage_explicite(self):
        reponse = self.client.post(reverse('vie_scolaire:creer_seance'), {
            'programme': self.programme.pk, 'date': '2026-09-28',
            'heure_debut': '08:00', 'heure_fin': '09:00',
        })
        self.assertEqual(reponse.status_code, 302)
        seance = Seance.objects.get()
        self.assertEqual(seance.classe_id, self.classe.pk)
        page = self.client.get(reverse('vie_scolaire:pointage_seance', args=[seance.pk]))
        self.assertEqual(page.context['non_pointes'], 2)
        self.assertEqual(Pointage.objects.count(), 0)
        appel = reverse('vie_scolaire:pointage_seance', args=[seance.pk])
        self.assertEqual(self.client.post(appel, self.donnees_pointage()).status_code, 302)
        self.assertEqual(Pointage.objects.count(), 0)
        self.assertEqual(self.client.post(appel, self.donnees_pointage(statut_a='absent')).status_code, 302)
        self.assertEqual(Pointage.objects.count(), 1)
        self.assertEqual(self.client.post(appel, self.donnees_pointage(statut_a='absent', statut_b='retard', minutes_b='7')).status_code, 302)
        page = self.client.get(appel)
        self.assertEqual((page.context['presents'], page.context['absents'], page.context['retards'], page.context['non_pointes']), (0, 1, 1, 0))
        self.assertEqual(Pointage.objects.get(inscription=self.inscription_b).minutes_retard, 7)

    def test_chevauchements_classe_et_enseignant_refuses(self):
        self.creer()
        url = reverse('vie_scolaire:creer_seance')
        classe = self.client.post(url, {
            'programme': self.programme.pk, 'date': '2026-09-28',
            'heure_debut': '08:30', 'heure_fin': '09:30',
        })
        self.assertEqual(classe.status_code, 200)
        self.assertContains(classe, 'chevauche')
        prof = self.client.post(url, {
            'programme': self.autre_programme.pk, 'date': '2026-09-28',
            'heure_debut': '08:30', 'heure_fin': '09:30',
        })
        self.assertEqual(prof.status_code, 200)
        self.assertContains(prof, 'déjà un cours')
        self.assertEqual(Seance.objects.count(), 1)

    def test_motif_decision_et_absence_restent_distincts(self):
        seance = self.creer()
        pointage = Pointage.objects.create(
            seance=seance, inscription=self.inscription_a, statut='absent', saisi_par=self.prof_user,
        )
        self.client.force_login(self.prof_user)
        url = reverse('vie_scolaire:justifier_pointage', args=[pointage.pk])
        self.assertEqual(self.client.post(url, {'motif': 'Maladie signalée'}).status_code, 302)
        justification = Justification.objects.get(pointage=pointage)
        self.assertEqual(justification.etat, Justification.Etat.ATTENTE)
        self.client.force_login(self.direction)
        decision = reverse('vie_scolaire:decider_justification', args=[justification.pk])
        self.assertEqual(self.client.post(decision, {'decision': 'validee', 'commentaire_decision': 'Accepté'}).status_code, 302)
        justification.refresh_from_db()
        pointage.refresh_from_db()
        self.assertEqual(justification.etat, Justification.Etat.VALIDEE)
        self.assertEqual(justification.decide_par_id, self.direction.pk)
        self.assertEqual(pointage.statut, Pointage.Statut.ABSENT)
        appel = reverse('vie_scolaire:pointage_seance', args=[seance.pk])
        page = self.client.post(appel, self.donnees_pointage(statut_a='present'))
        self.assertEqual(page.status_code, 200)
        pointage.refresh_from_db()
        self.assertEqual(pointage.statut, Pointage.Statut.ABSENT)

    def test_frontiere_ecole_et_droits_enseignant(self):
        seance = self.creer()
        appel = reverse('vie_scolaire:pointage_seance', args=[seance.pk])
        self.client.force_login(self.autre_user)
        self.assertEqual(self.client.get(appel).status_code, 404)
        self.client.force_login(self.prof_user)
        self.assertEqual(self.client.get(appel).status_code, 200)
        self.assertEqual(self.client.get(reverse('vie_scolaire:creer_seance')).status_code, 403)
        other = Seance.objects.create(
            ecole=self.ecole, classe=self.autre_classe, programme=self.autre_programme,
            enseignant=self.prof, date=date(2026, 9, 29), heure_debut=time(8), heure_fin=time(9),
        )
        self.assertEqual(self.client.get(reverse('vie_scolaire:pointage_seance', args=[other.pk])).status_code, 200)

    def test_contraintes_pointage_et_inscription(self):
        seance = self.creer()
        with self.assertRaises(ValidationError):
            Pointage.objects.create(seance=seance, inscription=self.inscription_a,
                                   statut='retard', minutes_retard=None)
        autre_inscription = Inscription.objects.create(
            ecole=self.ecole, etudiant=Etudiant.objects.create(
                ecole=self.ecole, nom='Koné', prenom='Sali', date_naissance=date(2012, 1, 1),
                genre='F', annee_scolaire_inscription=self.annee, classe=self.autre_classe,
            ), annee_scolaire=self.annee, classe=self.autre_classe,
            date_inscription=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            Pointage.objects.create(seance=seance, inscription=autre_inscription, statut='present')
        with self.assertRaises(ValidationError):
            Seance.objects.create(
                ecole=self.ecole, classe=self.classe, programme=self.programme,
                enseignant=self.prof, date=date(2027, 8, 1),
                heure_debut=time(10), heure_fin=time(11),
            )

    def test_enseignant_non_affecte_et_decision_interdite(self):
        seance = self.creer()
        non_affecte = get_user_model().objects.create_user(username='vs_prof_autre', password='unused')
        Profile.objects.create(user=non_affecte, ecole=self.ecole, role='teacher')
        Enseignant.objects.create(ecole=self.ecole, nom='Koné', prenom='Seydou', user=non_affecte)
        self.client.force_login(non_affecte)
        self.assertEqual(self.client.get(reverse('vie_scolaire:pointage_seance', args=[seance.pk])).status_code, 404)
        self.client.force_login(self.prof_user)
        pointage = Pointage.objects.create(seance=seance, inscription=self.inscription_a,
                                           statut='absent', saisi_par=self.prof_user)
        justification = Justification.objects.create(pointage=pointage, motif='Maladie', soumis_par=self.prof_user)
        self.assertEqual(self.client.get(reverse('vie_scolaire:decider_justification', args=[justification.pk])).status_code, 403)

    def test_formulaire_tronque_ne_cree_aucun_pointage(self):
        seance = self.creer()
        appel = reverse('vie_scolaire:pointage_seance', args=[seance.pk])
        tronque = self.donnees_pointage(statut_a='present')
        tronque['form-TOTAL_FORMS'] = '1'
        tronque['form-INITIAL_FORMS'] = '1'
        reponse = self.client.post(appel, tronque)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(Pointage.objects.count(), 0)

    def test_navigation_distincte_des_presences_journalieres(self):
        page = self.client.get(reverse('vie_scolaire:liste_seances'))
        self.assertEqual(page.status_code, 200)
        items = [item for section in page.context['shell_payload']['sections'] for item in section['items']]
        labels = {item['label'] for item in items}
        self.assertIn('Évaluations', labels)
        self.assertIn('Présences journalières', labels)
        self.assertIn('Appels par séance', labels)
        self.assertContains(page, 'registre journalier historique')
        fallback_nav = page.content.decode().split('<nav class="saas-menu"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('Appels par séance', fallback_nav)

    def test_inscription_suspendue_sans_pointage_ne_gonfle_pas_non_pointes(self):
        seance = self.creer()
        eleve_suspendu = Etudiant.objects.create(
            ecole=self.ecole, nom='Yattara', prenom='Fatou', date_naissance=date(2012, 6, 1),
            genre='F', annee_scolaire_inscription=self.annee, classe=self.classe,
        )
        inscription_suspendue = Inscription.objects.create(
            ecole=self.ecole, etudiant=eleve_suspendu, annee_scolaire=self.annee,
            classe=self.classe, date_inscription=date(2026, 9, 1), statut='suspendue',
        )
        appel = reverse('vie_scolaire:pointage_seance', args=[seance.pk])
        page = self.client.get(appel)
        self.assertEqual(page.context['total_eleves'], 2)
        self.assertEqual(page.context['non_pointes'], 2)
        # Reprise d'un ancien pointage conservé même sans affectation datée exploitable.
        Pointage.objects.bulk_create([Pointage(
            seance=seance, inscription=inscription_suspendue,
            statut='absent', saisi_par=self.admin,
        )])
        page = self.client.get(appel)
        self.assertEqual(page.context['total_eleves'], 3)
        self.assertEqual(page.context['absents'], 1)
        self.assertEqual(page.context['non_pointes'], 2)

    def test_transfert_date_conserve_ancien_appel_et_change_la_liste(self):
        ancienne_seance = self.creer()
        self.inscription_a.classe = self.autre_classe
        self.inscription_a.save(update_fields=['classe'])
        synchroniser_affectation(self.inscription_a, date_effet=date(2026, 9, 29))
        anciennes = list(AffectationClasse.objects.filter(
            inscription=self.inscription_a,
        ).order_by('date_debut').values_list('classe_id', 'date_debut', 'date_fin'))
        self.assertEqual(anciennes, [
            (self.classe.pk, date(2026, 9, 1), date(2026, 9, 29)),
            (self.autre_classe.pk, date(2026, 9, 29), None),
        ])
        Pointage.objects.create(
            seance=ancienne_seance, inscription=self.inscription_a,
            statut='absent', saisi_par=self.admin,
        )
        ancien_appel = self.client.get(reverse('vie_scolaire:pointage_seance', args=[ancienne_seance.pk]))
        self.assertEqual(ancien_appel.context['total_eleves'], 2)
        self.assertEqual(ancien_appel.context['absents'], 1)
        nouvelle_seance = Seance.objects.create(
            ecole=self.ecole, classe=self.autre_classe, programme=self.autre_programme,
            enseignant=self.prof, date=date(2026, 9, 29),
            heure_debut=time(8), heure_fin=time(9), cree_par=self.admin,
        )
        nouvel_appel = self.client.get(reverse('vie_scolaire:pointage_seance', args=[nouvelle_seance.pk]))
        self.assertEqual(nouvel_appel.context['total_eleves'], 1)
        self.assertEqual(nouvel_appel.context['non_pointes'], 1)
        Pointage.objects.create(
            seance=nouvelle_seance, inscription=self.inscription_a,
            statut='present', saisi_par=self.admin,
        )
        seance_classe_origine = Seance.objects.create(
            ecole=self.ecole, classe=self.classe, programme=self.programme,
            enseignant=self.prof, date=date(2026, 9, 29),
            heure_debut=time(9), heure_fin=time(10), cree_par=self.admin,
        )
        appel_origine = self.client.get(reverse('vie_scolaire:pointage_seance', args=[seance_classe_origine.pk]))
        self.assertEqual(appel_origine.context['total_eleves'], 1)
        with self.assertRaises(ValidationError):
            Pointage.objects.create(
                seance=seance_classe_origine, inscription=self.inscription_a,
                statut='present', saisi_par=self.admin,
            )
