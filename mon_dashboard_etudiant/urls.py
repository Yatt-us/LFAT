"""
URL configuration for mon_dashboard_etudiant project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# mon_dashboard_etudiant/urls.py
from dashboard.admin_site import site as admin_site
from dashboard.views.private_files import school_logo
from django.urls import path, include
from django.conf import settings
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin_site.urls),
    path('ecoles/<int:ecole_id>/logo/', school_logo, name='school_logo'),
    path('', include('dashboard.urls')),
    path('vie-scolaire/', include('vie_scolaire.urls')),




  # URLs d'authentification personnalisées
    path('accounts/login/', auth_views.LoginView.as_view(template_name='accounts/connexion.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('accounts/password_change/', auth_views.PasswordChangeView.as_view(template_name='accounts/password_change_form.html'), name='password_change'),
    path('accounts/password_change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='accounts/password_change_done.html'), name='password_change_done'),
    path('accounts/password_reset/', auth_views.PasswordResetView.as_view(template_name='accounts/password_reset_form.html'), name='password_reset'),
    path('accounts/password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('accounts/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    path('accounts/reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),

    # URL pour l'inscription (si vous avez une vue custom pour cela)
    # path('accounts/inscription/', ma_vue_inscription, name='inscription'),

    path('accounts/', include('django.contrib.auth.urls')), # Pour la gestion de l'authentification Django
]
