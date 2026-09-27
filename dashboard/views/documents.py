"""Vues documents du tableau de bord."""

import base64
import hashlib
import json
import qrcode
import secrets
from io import BytesIO

from django.contrib import messages
from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from weasyprint import HTML

from .common import *
from ..access import school_role_required
from ..document_templates import render_document_text
from ..models import ModeleDocument, DocumentEmis
from ..academic_calculations import BulletinCalculationError, bulletin_annuel, bulletin_trimestriel
from .private_files import _serve, private_file_data_uri


def _active_inscription(ecole, etudiant):
    year = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if year is None:
        return None, None
    inscription = get_object_or_404(
        Inscription.objects.select_related('classe', 'annee_scolaire'),
        ecole=ecole, etudiant=etudiant, annee_scolaire=year,
        statut='active', classe__isnull=False,
    )
    return year, inscription


def _document_values(ecole, etudiant, inscription, numero_document='', moyenne='', periode='', date_emission=None, lieu=None):
    date_emission = date_emission or timezone.localdate()
    return {
        'ecole_nom': ecole.nom_etablissement,
        'ecole_adresse': ecole.adresse_etablissement or '',
        'ecole_telephone': ecole.telephone or '',
        'eleve_nom_complet': f'{etudiant.prenom} {etudiant.nom}',
        'eleve_nom': etudiant.nom,
        'eleve_prenom': etudiant.prenom,
        'matricule': etudiant.numero_matricule or 'Non attribué',
        'classe': inscription.classe.nom_classe,
        'annee_scolaire': inscription.annee_scolaire.annee,
        'date_naissance': etudiant.date_naissance.strftime('%d/%m/%Y') if etudiant.date_naissance else '',
        'lieu_naissance': etudiant.lieu_naissance or '',
        'date_emission': date_emission.strftime('%d/%m/%Y'),
        'lieu_delivrance': lieu or ecole.commune or ecole.adresse_etablissement or '',
        'numero_document': numero_document,
        'nom_signataire': ecole.nom_signataire or '',
        'titre_signataire': ecole.titre_signataire or 'Le Directeur',
        'moyenne': moyenne,
        'periode': periode,
    }


def _qr_data_uri(url):
    if not url:
        return ''
    buffer = BytesIO()
    qrcode.make(url).save(buffer, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def _render_configured_pdf(request, modele, ecole, values, *, notes=None, qr_url='', mention_override=None, cachet=None, signature=None):
    values = dict(values)
    values['titre_signataire'] = render_document_text(modele.titre_signataire or '', values)
    fields = {
        field: render_document_text(getattr(modele, field) or '', values)
        for field in ('titre', 'entete', 'corps', 'pied_de_page', 'mention')
    }
    if mention_override:
        fields['mention'] = mention_override
    context = {
        **fields,
        'titre_signataire': values['titre_signataire'],
        'nom_signataire': values['nom_signataire'],
        'afficher_logo': modele.afficher_logo,
        'afficher_cachet': modele.afficher_cachet,
        'afficher_signature': modele.afficher_signature,
        'logo_data': private_file_data_uri(ecole.logo) if modele.afficher_logo else '',
        'cachet_data': private_file_data_uri(cachet or ecole.cachet_admin) if modele.afficher_cachet else '',
        'signature_data': private_file_data_uri(signature or ecole.signature_directeur) if modele.afficher_signature else '',
        'qr_data': _qr_data_uri(qr_url),
        'notes': notes or [],
        'moyenne': values.get('moyenne', ''),
        'numero_document': values.get('numero_document', ''),
        'date_emission': values.get('date_emission', ''),
        'periode': values.get('periode', ''),
    }
    html = render_to_string('dashboard/documents/document_pdf.html', context, request=request)
    base_url = request.build_absolute_uri('/') if request else '/'
    return HTML(string=html, base_url=base_url).write_pdf()


def _pdf_response(data, filename):
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response




def _issue_frequentation(request, certificat, inscription):
    """Render one immutable PDF for a school/year certificate."""
    ecole = inscription.ecole
    modele = ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_FREQUENTATION)
    if not modele.actif:
        return HttpResponse('Le modèle de certificat est désactivé.', status=409)
    certificat.ecole = ecole
    certificat.etudiant = inscription.etudiant
    certificat.annee_scolaire = inscription.annee_scolaire
    certificat.date_delivrance = certificat.date_delivrance or timezone.localdate()
    lieu = (certificat.lieu_delivrance or ecole.commune or ecole.adresse_etablissement or '').strip()
    if not lieu:
        return HttpResponse('Renseignez le lieu de délivrance du certificat ou la commune de l’école.', status=409)
    certificat.lieu_delivrance = lieu
    certificat.delivre_par = request.user
    if certificat.pk is None:
        # Hidden form fields must never choose an official verification token.
        certificat.code_verification = secrets.token_urlsafe(24)
        certificat.numero_certificat = f'CERT-{ecole.pk}-{inscription.etudiant_id}-{inscription.annee_scolaire_id}'
    else:
        certificat.code_verification = certificat.code_verification or secrets.token_urlsafe(24)
        certificat.numero_certificat = certificat.numero_certificat or (
            f'CERT-{ecole.pk}-{inscription.etudiant_id}-{inscription.annee_scolaire_id}'
        )
    # Only the seals configured for this school may appear on an official PDF.
    certificat.cachet_utilise = ecole.cachet_admin.name if ecole.cachet_admin else None
    certificat.signature_utilisee = ecole.signature_directeur.name if ecole.signature_directeur else None
    certificat.statut = 'valide'
    certificat.ministere = ecole.ministere or ''
    certificat.academie = ecole.academie or ''
    certificat.etablissement_reference = ecole.nom_etablissement
    certificat.adresse_etablissement = ecole.adresse_etablissement or ''
    values = _document_values(
        ecole, inscription.etudiant, inscription,
        numero_document=certificat.numero_certificat,
        date_emission=certificat.date_delivrance,
        lieu=certificat.lieu_delivrance,
    )
    qr_url = request.build_absolute_uri(
        reverse('verifier_certificat', args=[certificat.code_verification])
    )
    pdf_data = _render_configured_pdf(
        request, modele, ecole, values, qr_url=qr_url,
        mention_override=certificat.mention_legale,
        cachet=certificat.cachet_utilise, signature=certificat.signature_utilisee,
    )
    qr_buffer = BytesIO()
    qrcode.make(qr_url).save(qr_buffer, format='PNG')
    base_name = f'certificat_{inscription.etudiant_id}_{inscription.annee_scolaire_id}'
    certificat.qr_code.save(f'qr_{base_name}.png', ContentFile(qr_buffer.getvalue()), save=False)
    certificat.fichier_pdf.save(f'{base_name}.pdf', ContentFile(pdf_data), save=False)
    certificat.save()
    return _pdf_response(pdf_data, f'{base_name}.pdf')


@school_role_required('school_admin', 'director', 'secretary')
@require_http_methods(['GET', 'POST'])
def generer_certificat_frequentation(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee_active, inscription = _active_inscription(ecole, etudiant)
    if annee_active is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    certificat = CertificatFrequentation.objects.filter(
        etudiant=etudiant, annee_scolaire=annee_active,
    ).first()
    if certificat is not None:
        if certificat.ecole_id != ecole.pk:
            return HttpResponse('Certificat lié à une autre école.', status=403)
        if certificat.statut != 'valide':
            return HttpResponse('Ce certificat a été annulé ou archivé.', status=409)
        if certificat.fichier_pdf and certificat.fichier_pdf.storage.exists(certificat.fichier_pdf.name):
            return _serve(certificat.fichier_pdf, download=True)
    if request.method == 'GET':
        return redirect(f"{reverse('creer_certificat_interface')}?etudiant_id={etudiant.pk}")
    if not ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_FREQUENTATION).actif:
        return HttpResponse('Le modèle de certificat est désactivé.', status=409)
    if certificat is None:
        certificat = CertificatFrequentation(
            ecole=ecole, etudiant=etudiant, annee_scolaire=annee_active,
            date_delivrance=timezone.localdate(), delivre_par=request.user,
        )
    return _issue_frequentation(request, certificat, inscription)


@school_role_required('school_admin', 'director', 'secretary')
def creer_certificat_interface(request):
    """Collect optional certificate metadata and issue the configured school layout."""
    ecole = get_user_ecole(request)
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if annee_active is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    initial_data = {}
    etudiant_id = request.GET.get('etudiant_id')
    if etudiant_id:
        initial_data['etudiant'] = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)

    if request.method == 'POST':
        form = CertificatFrequentationForm(request.POST, request.FILES, user=request.user, ecole=ecole)
        if form.is_valid():
            certificat = form.save(commit=False)
            etudiant = certificat.etudiant
            inscription = Inscription.objects.select_related('classe', 'annee_scolaire').filter(
                ecole=ecole, etudiant=etudiant, annee_scolaire=annee_active,
                statut='active', classe__isnull=False,
            ).first()
            if inscription is None:
                form.add_error('etudiant', "Cet élève n'est pas inscrit dans une classe pour l'année active.")
            else:
                existant = CertificatFrequentation.objects.filter(
                    etudiant=etudiant, annee_scolaire=annee_active,
                ).first()
                if existant and existant.ecole_id != ecole.pk:
                    form.add_error('etudiant', 'Le certificat existant appartient à une autre école.')
                elif existant and (existant.statut != 'valide' or (
                    existant.fichier_pdf and existant.fichier_pdf.storage.exists(existant.fichier_pdf.name)
                )):
                    form.add_error('etudiant', 'Un certificat a déjà été émis pour cet élève et cette année.')
                else:
                    if existant:
                        for champ in ('date_delivrance', 'lieu_delivrance', 'mention_legale', 'remarque'):
                            setattr(existant, champ, getattr(certificat, champ))
                        certificat = existant
                    return _issue_frequentation(request, certificat, inscription)
    else:
        form = CertificatFrequentationForm(initial=initial_data, user=request.user, ecole=ecole)
    return render(request, 'dashboard/etudiants/creer_certificat.html', {'form': form})


# ----------------------------------
# les views de paiement 
#------------------------------


def _document_fingerprint(modele, ecole, etudiant, inscription, *, periode='', notes=None, moyenne=''):
    """Reuse a valid PDF while its plan and source data remain identical."""
    source = {
        'modele': modele.as_snapshot(),
        'ecole': {
            'id': ecole.pk, 'nom': ecole.nom_etablissement,
            'adresse': ecole.adresse_etablissement,
            'telephone': ecole.telephone, 'commune': ecole.commune,
            'nom_signataire': ecole.nom_signataire,
            'titre_signataire': ecole.titre_signataire,
            'logo': ecole.logo.name, 'cachet': ecole.cachet_admin.name,
            'signature': ecole.signature_directeur.name,
        },
        'eleve': {
            'id': etudiant.pk, 'nom': etudiant.nom, 'prenom': etudiant.prenom,
            'matricule': etudiant.numero_matricule,
            'date_naissance': etudiant.date_naissance.isoformat() if etudiant.date_naissance else None,
            'lieu_naissance': etudiant.lieu_naissance,
        },
        'inscription': {
            'id': inscription.pk, 'classe': inscription.classe.nom_classe,
            'annee': inscription.annee_scolaire.annee,
        },
        'periode': periode,
        'notes': notes or [],
    }
    if moyenne:
        source['moyenne'] = moyenne
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _issue_archived_document(request, modele, etudiant, inscription, *, periode='', notes=None, moyenne=''):
    ecole = inscription.ecole
    if not modele.actif:
        return HttpResponse('Ce modèle de document est désactivé.', status=409)
    rows = notes or []
    fingerprint = _document_fingerprint(
        modele, ecole, etudiant, inscription, periode=periode, notes=rows, moyenne=moyenne,
    )
    with transaction.atomic():
        # Serialise repeated clicks for the same pupil on databases supporting row locks.
        Etudiant.objects.select_for_update().get(pk=etudiant.pk, ecole=ecole)
        existing = DocumentEmis.objects.filter(
            ecole=ecole, etudiant=etudiant,
            annee_scolaire=inscription.annee_scolaire,
            inscription=inscription, type_document=modele.type_document,
            statut=DocumentEmis.STATUT_VALIDE,
            donnees_snapshot__empreinte=fingerprint,
        ).order_by('-date_emission').first()
        if existing and existing.fichier_pdf and existing.fichier_pdf.storage.exists(existing.fichier_pdf.name):
            return _serve(existing.fichier_pdf, download=True)

        if modele.type_document == ModeleDocument.TYPE_BULLETIN:
            # Only one published bulletin per pupil, year and period is current.
            # Previously issued files remain archived but their QR is revoked.
            DocumentEmis.objects.filter(
                ecole=ecole, etudiant=etudiant,
                annee_scolaire=inscription.annee_scolaire,
                inscription=inscription, type_document=ModeleDocument.TYPE_BULLETIN,
                statut=DocumentEmis.STATUT_VALIDE,
                donnees_snapshot__periode=periode,
            ).update(
                statut=DocumentEmis.STATUT_ANNULE,
                annule_le=timezone.now(), annule_par=request.user,
                motif_annulation='Remplacé par une nouvelle publication du bulletin.',
            )

        document = DocumentEmis(
            ecole=ecole, etudiant=etudiant,
            annee_scolaire=inscription.annee_scolaire,
            inscription=inscription, emis_par=request.user,
        )
        document.capturer_modele(modele)
        document.donnees_snapshot = {'empreinte': fingerprint}
        document.save()
        values = _document_values(
            ecole, etudiant, inscription,
            numero_document=document.numero_document,
            date_emission=timezone.localtime(document.date_emission).date(),
            moyenne=moyenne, periode=periode,
        )
        verification_url = request.build_absolute_uri(
            reverse('verifier_document', args=[document.code_verification])
        )
        pdf_data = _render_configured_pdf(
            request, modele, ecole, values, notes=rows, qr_url=verification_url,
        )
        document.donnees_snapshot = {
            **values, 'empreinte': fingerprint, 'notes': rows,
        }
        filename = f'{modele.type_document}_{document.numero_document}.pdf'
        document.fichier_pdf.save(filename, ContentFile(pdf_data), save=False)
        document.save(update_fields=['donnees_snapshot', 'fichier_pdf'])
    return _pdf_response(pdf_data, filename)


@school_role_required('school_admin', 'director')
@require_http_methods(['GET', 'POST'])
def generer_bulletin_scolaire(request, etudiant_id, periode):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    if periode not in dict(Note.PERIODE_EVALUATION_CHOICES):
        return HttpResponse('Période invalide.', status=400)
    annee, inscription = _active_inscription(ecole, etudiant)
    if annee is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    try:
        rows, moyenne = (
            bulletin_annuel(inscription) if periode == 'Annuelle'
            else bulletin_trimestriel(inscription, periode)
        )
    except BulletinCalculationError as exc:
        return HttpResponse(str(exc), status=409)
    modele = ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_BULLETIN)
    if not modele.actif:
        return HttpResponse('Le modèle de bulletin est désactivé.', status=409)
    if request.method == 'GET':
        values = _document_values(ecole, etudiant, inscription, moyenne=moyenne, periode=periode)
        return render(request, 'dashboard/documents/apercu_bulletin.html', {
            'etudiant': etudiant, 'inscription': inscription,
            'periode': periode, 'notes': rows, 'moyenne': moyenne,
            'titre': render_document_text(modele.titre, values),
            'entete': render_document_text(modele.entete, values),
            'corps': render_document_text(modele.corps, values),
            'mention': render_document_text(modele.mention, values),
            'titre_signataire': render_document_text(modele.titre_signataire, values),
        })
    return _issue_archived_document(
        request, modele, etudiant, inscription,
        periode=periode, notes=rows, moyenne=moyenne,
    )


@school_role_required('school_admin', 'director')
@require_POST
def annuler_document_emis(request, document_id):
    ecole = get_user_ecole(request)
    motif = (request.POST.get('motif') or '').strip()
    if not motif:
        return HttpResponse("Le motif de l'annulation est obligatoire.", status=400)
    if len(motif) > 500:
        return HttpResponse("Le motif de l'annulation ne peut pas dépasser 500 caractères.", status=400)
    with transaction.atomic():
        document = get_object_or_404(
            DocumentEmis.objects.select_for_update(), pk=document_id, ecole=ecole,
        )
        if document.statut == DocumentEmis.STATUT_VALIDE:
            document.statut = DocumentEmis.STATUT_ANNULE
            document.annule_le = timezone.now()
            document.annule_par = request.user
            document.motif_annulation = motif
            document.save(update_fields=[
                'statut', 'annule_le', 'annule_par', 'motif_annulation',
            ])
            messages.success(request, 'Le document a été annulé ; son code de vérification le signale désormais.')
        else:
            messages.info(request, 'Ce document est déjà annulé.')
    return redirect('detail_etudiant', etudiant_id=document.etudiant_id)


@school_role_required('school_admin', 'director', 'secretary')
@require_POST
def generer_attestation_scolarite(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee, inscription = _active_inscription(ecole, etudiant)
    if annee is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    modele = ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_ATTESTATION)
    return _issue_archived_document(request, modele, etudiant, inscription)


@school_role_required('school_admin', 'director', 'secretary')
@require_POST
def generer_certificat_inscription(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee, inscription = _active_inscription(ecole, etudiant)
    if annee is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    modele = ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_INSCRIPTION)
    return _issue_archived_document(request, modele, etudiant, inscription)


@school_role_required('school_admin', 'director', 'secretary')
@require_POST
def generer_document_personnalise(request, etudiant_id, modele_id):
    ecole = get_user_ecole(request)
    modele = get_object_or_404(
        ModeleDocument, pk=modele_id, ecole=ecole,
        type_document=ModeleDocument.TYPE_AUTRE, actif=True,
    )
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee, inscription = _active_inscription(ecole, etudiant)
    if annee is None:
        return HttpResponse('Aucune année scolaire active pour cette école.', status=400)
    return _issue_archived_document(request, modele, etudiant, inscription)


def verifier_document(request, code_verification):
    """Public QR verification without exposing the archived PDF or pupil profile."""
    document = get_object_or_404(
        DocumentEmis.objects.select_related('ecole', 'annee_scolaire'),
        code_verification=code_verification,
    )
    response = render(request, 'dashboard/documents/verification_document.html', {
        'document': document, 'valide': document.statut == DocumentEmis.STATUT_VALIDE,
    })
    response['Cache-Control'] = 'no-store'
    return response


# ======================================================
# Liste et filtrage des notes par classe et matière
# ======================================================


@school_role_required('school_admin', 'director', 'secretary')
def carte_scolaire(request, etudiant_id, pdf=False):
    """Émet une carte liée à l'inscription active de l'élève."""
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if annee_active is None:
        return HttpResponse("Aucune année scolaire active pour cette école.", status=400)
    inscription = get_object_or_404(
        Inscription.objects.select_related('classe', 'annee_scolaire'),
        etudiant=etudiant, ecole=ecole, annee_scolaire=annee_active,
        statut='active', classe__isnull=False,
    )
    token = signing.dumps({
        'etudiant_id': etudiant.pk,
        'ecole_id': ecole.pk,
        'inscription_id': inscription.pk,
    }, salt='carte-scolaire')
    qr_url = request.build_absolute_uri(reverse('verification_carte_scolaire', args=[token]))
    qr_buffer = BytesIO()
    qrcode.make(qr_url).save(qr_buffer, format='PNG')
    qr_base64 = 'data:image/png;base64,' + base64.b64encode(qr_buffer.getvalue()).decode('ascii')
    if pdf:
        sources = {
            'logo_source': private_file_data_uri(ecole.logo),
            'photo_source': private_file_data_uri(etudiant.photo_profil),
            'cachet_source': private_file_data_uri(ecole.cachet_admin),
            'signature_source': private_file_data_uri(ecole.signature_directeur),
        }
    else:
        sources = {
            'logo_source': reverse('school_logo', args=[ecole.pk]) if ecole.logo else '',
            'photo_source': reverse('student_photo', args=[etudiant.pk]) if etudiant.photo_profil else '',
            'cachet_source': reverse('school_asset', args=[ecole.pk, 'cachet']) if ecole.cachet_admin else '',
            'signature_source': reverse('school_asset', args=[ecole.pk, 'signature']) if ecole.signature_directeur else '',
        }
    context = {
        'etudiant': etudiant, 'ecole': ecole, 'classe': inscription.classe,
        'annee_scolaire': inscription.annee_scolaire, 'qr_code': qr_base64,
        **sources,
    }
    if pdf:
        html = render_to_string('dashboard/cartes/carte_scolaire.html', context, request=request)
        pdf_content = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="carte_{etudiant.pk}_{annee_active.pk}.pdf"'
        return response
    return render(request, 'dashboard/cartes/carte_scolaire.html', context)


@school_role_required('school_admin', 'director', 'secretary')
def verifier_etudiant(request, etudiant_id):
    """Contrôle interne de l'inscription active d'un élève."""
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    inscription = get_object_or_404(
        Inscription.objects.select_related('classe', 'annee_scolaire'),
        etudiant=etudiant, ecole=ecole, annee_scolaire__active=True,
        statut='active', classe__isnull=False,
    )
    return render(request, 'dashboard/cartes/verification_eleve.html', {
        'etudiant': etudiant, 'ecole': ecole,
        'classe': inscription.classe, 'annee_scolaire': inscription.annee_scolaire,
    })


def verification_carte_scolaire(request, token):
    """Vérification publique d'une carte liée à une inscription encore active."""
    try:
        payload = signing.loads(token, salt='carte-scolaire', max_age=60 * 60 * 24 * 400)
    except signing.SignatureExpired:
        return HttpResponse('Cette carte a expiré.', status=410)
    except signing.BadSignature:
        return HttpResponse('Code de vérification invalide.', status=404)
    if not isinstance(payload, dict) or not payload.get('inscription_id'):
        return HttpResponse('Cette carte doit être renouvelée.', status=410)
    inscription = get_object_or_404(
        Inscription.objects.select_related('etudiant', 'ecole', 'classe', 'annee_scolaire'),
        pk=payload['inscription_id'], etudiant_id=payload.get('etudiant_id'),
        ecole_id=payload.get('ecole_id'), etudiant__ecole_id=payload.get('ecole_id'),
        annee_scolaire__ecole_id=payload.get('ecole_id'), annee_scolaire__active=True,
        statut='active', classe__isnull=False,
    )
    return render(request, 'dashboard/cartes/verification_eleve.html', {
        'etudiant': inscription.etudiant, 'ecole': inscription.ecole,
        'classe': inscription.classe, 'annee_scolaire': inscription.annee_scolaire,
    })


def verifier_certificat(request, code_verification):
    """Vérification publique d'un certificat via son code aléatoire."""
    certificat = get_object_or_404(
        CertificatFrequentation.objects.select_related('ecole', 'etudiant', 'annee_scolaire'),
        code_verification=code_verification,
    )
    return render(request, 'dashboard/cartes/verification_certificat.html', {
        'certificat': certificat, 'valide': certificat.is_valide(),
    })


@school_role_required('school_admin', 'director')
def generer_bulletins_classe_vue(request, classe_id, periode):
    """Aperçu et lancement de la génération en masse des bulletins officiels pour une classe."""
    ecole = get_user_ecole(request)
    classe = get_object_or_404(
        Classe.objects.select_related('annee_scolaire'),
        pk=classe_id,
        ecole=ecole,
    )
    periodes_valides = dict(Note.PERIODE_EVALUATION_CHOICES)
    if periode not in periodes_valides:
        return HttpResponse('Période invalide.', status=400)

    from ..bulletin_automation import automatiser_bulletins_classe
    from ..academic_calculations import calculer_classement_classe

    if request.method == 'POST':
        notifier = request.POST.get('notifier_parents') in ('1', 'true', 'True', 'on')
        try:
            resultats = automatiser_bulletins_classe(
                request, classe, periode, user=request.user, notifier_parents=notifier
            )
            nb_succes = len(resultats['succes'])
            nb_erreurs = len(resultats['erreurs'])
            if nb_succes > 0:
                messages.success(
                    request,
                    f"Génération terminée : {nb_succes} bulletin(s) officiel(s) émis, signés et archivés avec succès."
                )
            if nb_erreurs > 0:
                messages.warning(
                    request,
                    f"{nb_erreurs} élève(s) ont des notes incomplètes ou manquantes pour cette période."
                )
        except Exception as exc:
            messages.error(request, f"Erreur lors de la génération des bulletins : {exc}")
        return redirect('automatiser_bulletins_classe', classe_id=classe.pk, periode=periode)

    classement_info = calculer_classement_classe(classe, periode)

    bulletins_emis = {
        doc.inscription_id: doc
        for doc in DocumentEmis.objects.filter(
            ecole=ecole,
            inscription__classe=classe,
            annee_scolaire=classe.annee_scolaire,
            type_document=ModeleDocument.TYPE_BULLETIN,
            statut=DocumentEmis.STATUT_VALIDE,
            donnees_snapshot__periode=periode,
        ).select_related('etudiant')
    }

    nb_bulletins_generes = len(bulletins_emis)

    eleves_data = []
    for item in classement_info.get('resultats', []):
        insc = item['inscription']
        eleves_data.append({
            'inscription': insc,
            'etudiant': insc.etudiant,
            'moyenne': item['moyenne'],
            'rang': item['rang'],
            'mention': item['mention'],
            'decision_recommandee': item.get('decision_recommandee'),
            'nb_matieres': len(item['bulletin_lignes']),
            'document': bulletins_emis.get(insc.pk),
        })

    context = {
        'classe': classe,
        'periode': periode,
        'periode_label': periodes_valides.get(periode, periode),
        'periodes_disponibles': Note.PERIODE_EVALUATION_CHOICES,
        'effectif': classement_info.get('effectif', 0),
        'moyenne_classe': classement_info.get('moyenne_classe', 0),
        'moyenne_max': classement_info.get('moyenne_max', 0),
        'moyenne_min': classement_info.get('moyenne_min', 0),
        'eleves_data': eleves_data,
        'erreurs': classement_info.get('erreurs', []),
        'nb_bulletins_generes': nb_bulletins_generes,
    }
    return render(request, 'dashboard/bulletins/automatisation_bulletins_classe.html', context)


@school_role_required('school_admin', 'director')
def telecharger_bulletins_zip_vue(request, classe_id, periode):
    """Téléchargement d'une archive ZIP contenant tous les bulletins officiels PDF d'une classe."""
    ecole = get_user_ecole(request)
    classe = get_object_or_404(
        Classe.objects.select_related('annee_scolaire'),
        pk=classe_id,
        ecole=ecole,
    )
    from ..bulletin_automation import creer_zip_bulletins_classe
    zip_buffer = creer_zip_bulletins_classe(classe, periode)
    nom_fichier = f"Bulletins_{classe.nom_classe}_{periode}.zip".replace(' ', '_')
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    return response
