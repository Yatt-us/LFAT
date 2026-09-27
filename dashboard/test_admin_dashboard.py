"""Checks for the platform-only Angular dashboard context."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import DemandeAbonnement, EcoleSettings


class PlatformAdminDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.active_school = EcoleSettings.objects.create(
            nom_etablissement='École active',
            statut_abonnement='active',
            date_fin_abonnement=now + timedelta(days=30),
        )
        EcoleSettings.objects.create(nom_etablissement='École en essai')
        cls.expired_school = EcoleSettings.objects.create(
            nom_etablissement='École expirée',
            statut_abonnement='expired',
        )
        EcoleSettings.objects.create(
            nom_etablissement='École suspendue',
            statut_abonnement='suspended',
            est_active=False,
        )
        DemandeAbonnement.objects.create(ecole=cls.expired_school, montant=25000)
        DemandeAbonnement.objects.create(
            ecole=cls.active_school, montant=25000, statut='paid', confirme_le=now,
        )
        User = get_user_model()
        cls.superuser = User.objects.create_superuser(
            username='platform_admin_example', password='test-password', email='platform@example.test',
        )
        cls.school_staff = User.objects.create_user(
            username='school_staff_example', password='test-password', is_staff=True,
        )

    def test_superuser_sees_global_indicators_and_admin_links(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'admin/platform_index.html')
        data = response.context['platform_dashboard_data']
        self.assertEqual(data['summary'], {
            'schools': 4, 'access': 2, 'pending': 1, 'revenue': 25000.0,
        })
        self.assertEqual(
            {item['key']: item['count'] for item in data['access']},
            {'active': 1, 'trial': 1, 'expired': 1, 'suspended': 1},
        )
        self.assertEqual(len(data['monthly']), 6)
        self.assertEqual(data['monthly'][-1]['submitted'], 2)
        self.assertEqual(data['monthly'][-1]['confirmed'], 1)
        self.assertEqual(data['pending'][0]['school'], 'École expirée')
        self.assertEqual(
            data['links']['requests'], reverse('admin:dashboard_demandeabonnement_changelist'),
        )
        self.assertContains(response, 'platform-admin-data')

    def test_school_staff_cannot_access_platform_dashboard(self):
        self.client.force_login(self.school_staff)
        response = self.client.get(reverse('admin:index'))
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn('platform_dashboard_data', getattr(response, 'context', {}) or {})
