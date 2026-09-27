# dashboard/views.py
import base64
import os
import shutil
import tempfile
from textwrap import wrap
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required , user_passes_test
from django.db.models import Sum, Count, Avg, Prefetch
from django.http import HttpResponse
from django.db import transaction # Pour gérer les transactions de base de données
from django.forms import ValidationError, modelformset_factory # Pour gérer plusieurs formulaires d'un même modèle
from django.forms import formset_factory
from django.utils import timezone
# Pour la génération de PDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from datetime import datetime, timedelta
from datetime import date
from reportlab.lib.units import inch
from django.core.files.base import ContentFile
import io
import os # Pour extraire le nom de base du fichier d'asset
import qrcode
from weasyprint import HTML
from wkhtmltopdf.views import PDFTemplateResponse
from django.template.loader import render_to_string
import pdfkit  
from django_pdfkit import PDFView

from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, black
from django.db.models import Avg, Min, Max
import csv
import openpyxl

# Importation de ReportLab
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader



from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Table, TableStyle

# Importez tous vos formulaires
from ..forms import (
    CertificatFrequentationForm, EcoleSettingsForm, EmploiDuTempsForm, EtudiantForm, DossierInscriptionImageForm, NoteForm, PaiementForm, PresenceForm, InscriptionForm,
    EnseignantForm, MatiereForm, ClasseForm, ProgrammeMatiereForm, AnneeScolaireForm, InscriptionForm
)

# Importez tous vos modèles
from ..models import (
    EcoleSettings, EmploiDuTemps, Etudiant, AnneeScolaire, Enseignant, Classe, Matiere, ProgrammeMatiere, DemandeAbonnement, Inscription,
    Note, Paiement, CreanceScolaire, Presence, DossierInscriptionImage, CertificatFrequentation , Profile
)

from django.db.models import Q  # Pour les recherches complexes



# Helpers partagés par les vues du tableau de bord.
from dashboard.tenant import school_for_user


def get_user_ecole(request):
    """Retourne l'école unique associée au compte connecté."""
    return school_for_user(request.user)
