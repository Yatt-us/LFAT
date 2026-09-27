"""Regression checks for the blocked-school sign-in journey."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import DemandeAbonnement, EcoleSettings, Profile


class SubscriptionWaitingFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = EcoleSettings.objects.create(nom_etablissement='École en attente')
        cls.school.est_active = False
        cls.school.statut_abonnement = 'suspended'
        cls.school.save(update_fields=['est_active', 'statut_abonnement'])
        user_model = get_user_model()
        cls.director = user_model.objects.create_user(username='director_waiting', password='test-password')
        cls.secretary = user_model.objects.create_user(username='secretary_waiting', password='test-password')
        Profile.objects.create(user=cls.director, ecole=cls.school, role='director')
        Profile.objects.create(user=cls.secretary, ecole=cls.school, role='secretary')

    def test_pending_request_can_return_to_login(self):
        DemandeAbonnement.objects.create(ecole=self.school, montant=25000)
        self.client.force_login(self.director)
        self.assertRedirects(
            self.client.get(reverse('dashboard_accueil')),
            reverse('initier_paiement'),
            fetch_redirect_response=False,
        )
        waiting_page = self.client.get(reverse('initier_paiement'))
        self.assertContains(waiting_page, 'Votre demande est en attente')
        self.assertContains(waiting_page, 'Se déconnecter et revenir à la connexion')
        self.assertNotContains(waiting_page, 'Retour au tableau de bord')
        self.assertRedirects(
            self.client.post(reverse('logout')),
            reverse('login'),
            fetch_redirect_response=False,
        )
        self.assertContains(self.client.get(reverse('login')), 'Connexion')

    def test_other_school_roles_can_see_status_but_cannot_submit(self):
        self.client.force_login(self.secretary)
        self.assertRedirects(
            self.client.get(reverse('dashboard_accueil')),
            reverse('initier_paiement'),
            fetch_redirect_response=False,
        )
        waiting_page = self.client.get(reverse('initier_paiement'))
        self.assertEqual(waiting_page.status_code, 200)
        self.assertContains(waiting_page, 'Se déconnecter et revenir à la connexion')
        self.assertNotContains(waiting_page, 'Soumettre une demande')
        self.assertEqual(self.client.post(reverse('initier_paiement')).status_code, 403)
        self.assertFalse(DemandeAbonnement.objects.exists())

    def test_director_can_submit_once_and_wait_for_confirmation(self):
        self.client.force_login(self.director)
        self.assertRedirects(
            self.client.post(reverse('initier_paiement')),
            reverse('initier_paiement'),
            fetch_redirect_response=False,
        )
        self.assertEqual(DemandeAbonnement.objects.filter(ecole=self.school, statut='pending').count(), 1)
        self.assertContains(self.client.get(reverse('initier_paiement')), 'Votre demande est en attente')
        self.client.post(reverse('initier_paiement'))
        self.assertEqual(DemandeAbonnement.objects.filter(ecole=self.school, statut='pending').count(), 1)
