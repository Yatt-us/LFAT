from django.urls import path
from . import views

app_name = 'vie_scolaire'

urlpatterns = [
    path('', views.liste_seances, name='liste_seances'),
    path('seances/creer/', views.creer_seance, name='creer_seance'),
    path('seances/<int:seance_id>/appel/', views.pointage_seance, name='pointage_seance'),
    path('pointages/<int:pointage_id>/justifier/', views.justifier_pointage, name='justifier_pointage'),
    path('justifications/<int:justification_id>/decider/', views.decider_justification, name='decider_justification'),
]
