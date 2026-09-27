from datetime import datetime, time

from django.contrib.admin import AdminSite
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils import timezone

from .models import DemandeAbonnement, EcoleSettings


def _month_at_offset(today, offset):
    month_index = today.year * 12 + today.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return today.replace(year=year, month=zero_based_month + 1, day=1)


def _effective_access(ecole):
    if not ecole.peut_utiliser_systeme():
        if not ecole.est_active or ecole.statut_abonnement == 'suspended':
            return 'suspended'
        return 'expired'
    return ecole.statut_abonnement


class RestrictedAdminSite(AdminSite):
    """Administration globale réservée à l’équipe plateforme."""

    index_template = 'admin/platform_index.html'

    def has_permission(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def index(self, request, extra_context=None):
        if not self.has_permission(request):
            raise PermissionDenied

        today = timezone.localdate()
        now = timezone.now()
        first_month = _month_at_offset(today, -5)
        start = timezone.make_aware(datetime.combine(first_month, time.min))
        current_month_start = timezone.make_aware(
            datetime.combine(today.replace(day=1), time.min)
        )

        access_labels = {
            'active': 'Abonnement actif',
            'trial': 'Essai en cours',
            'expired': 'Accès expiré',
            'suspended': 'Accès suspendu',
        }
        access_counts = {key: 0 for key in access_labels}
        for ecole in EcoleSettings.objects.only(
            'statut_abonnement', 'date_fin_abonnement', 'date_fin_essai', 'est_active'
        ).iterator():
            access_counts[_effective_access(ecole)] += 1

        monthly = []
        months = {}
        for offset in range(-5, 1):
            month = _month_at_offset(today, offset)
            entry = {
                'month': month.strftime('%Y-%m'),
                'label': month.strftime('%m/%Y'),
                'submitted': 0,
                'confirmed': 0,
            }
            monthly.append(entry)
            months[entry['month']] = entry

        submitted_by_month = (
            DemandeAbonnement.objects.filter(cree_le__gte=start, cree_le__lte=now)
            .annotate(month=TruncMonth('cree_le'))
            .values('month')
            .annotate(total=Count('pk'))
        )
        for row in submitted_by_month:
            month = timezone.localtime(row['month']).strftime('%Y-%m')
            if month in months:
                months[month]['submitted'] = row['total']

        confirmed_by_month = (
            DemandeAbonnement.objects.filter(
                statut='paid', confirme_le__gte=start, confirme_le__lte=now
            )
            .annotate(month=TruncMonth('confirme_le'))
            .values('month')
            .annotate(total=Count('pk'))
        )
        for row in confirmed_by_month:
            month = timezone.localtime(row['month']).strftime('%Y-%m')
            if month in months:
                months[month]['confirmed'] = row['total']

        pending_query = DemandeAbonnement.objects.filter(statut='pending')
        pending = [
            {
                'school': demande.ecole.nom_etablissement,
                'date': timezone.localtime(demande.cree_le).strftime('%d/%m/%Y'),
                'amount': float(demande.montant),
                'href': reverse('admin:dashboard_demandeabonnement_change', args=[demande.pk]),
            }
            for demande in pending_query.select_related('ecole').order_by('-cree_le', '-pk')[:5]
        ]
        revenue = (
            DemandeAbonnement.objects.filter(
                statut='paid', confirme_le__gte=current_month_start, confirme_le__lte=now
            ).aggregate(total=Sum('montant'))['total']
            or 0
        )

        dashboard_data = {
            'viewer': {
                'name': request.user.get_full_name().strip() or request.user.username,
                'username': request.user.username,
            },
            'summary': {
                'schools': sum(access_counts.values()),
                'access': access_counts['active'] + access_counts['trial'],
                'pending': pending_query.count(),
                'revenue': float(revenue),
            },
            'access': [
                {'key': key, 'label': label, 'count': access_counts[key]}
                for key, label in access_labels.items()
            ],
            'monthly': monthly,
            'pending': pending,
            'links': {
                'schools': reverse('admin:dashboard_ecolesettings_changelist'),
                'requests': reverse('admin:dashboard_demandeabonnement_changelist'),
                'users': reverse('admin:auth_user_changelist'),
                'documents': reverse('admin:dashboard_documentemis_changelist'),
                'passwordChange': reverse('admin:password_change'),
                'logout': reverse('admin:logout'),
            },
            'csrfToken': get_token(request),
        }
        return super().index(
            request, extra_context={**(extra_context or {}), 'platform_dashboard_data': dashboard_data}
        )


site = RestrictedAdminSite(name='admin')
