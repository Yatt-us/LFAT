"""Authenticated downloads for student and school records."""
import base64
import mimetypes
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from ..access import school_role_required
from ..models import CertificatFrequentation, DocumentEmis, DossierInscriptionImage, EcoleSettings, Etudiant
from ..tenant import school_for_user


STAFF_ROLES = ('school_admin', 'director', 'secretary')


def _serve(field, *, download=False):
    if not field:
        raise Http404('Fichier absent.')
    try:
        opened = field.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        raise Http404('Fichier absent.')
    mime = mimetypes.guess_type(field.name)[0] or 'application/octet-stream'
    response = FileResponse(opened, content_type=mime, as_attachment=download)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = 'sandbox'
    return response


def private_file_data_uri(field):
    """Embed trusted, authenticated assets in server-rendered PDFs."""
    if not field:
        return ''
    try:
        with field.open('rb') as opened:
            data = opened.read()
    except (FileNotFoundError, OSError, ValueError):
        return ''
    mime = mimetypes.guess_type(field.name)[0] or 'application/octet-stream'
    return f'data:{mime};base64,{base64.b64encode(data).decode("ascii")}'


@school_role_required(*STAFF_ROLES)
def student_photo(request, etudiant_id):
    school = school_for_user(request.user)
    student = get_object_or_404(Etudiant, pk=etudiant_id, ecole=school)
    return _serve(student.photo_profil)


@school_role_required(*STAFF_ROLES)
def enrollment_document(request, document_id):
    school = school_for_user(request.user)
    document = get_object_or_404(
        DossierInscriptionImage, pk=document_id, ecole=school, etudiant__ecole=school,
    )
    return _serve(document.image, download=True)


@school_role_required(*STAFF_ROLES)
def certificate_file(request, certificat_id):
    school = school_for_user(request.user)
    certificate = get_object_or_404(
        CertificatFrequentation, pk=certificat_id, ecole=school, etudiant__ecole=school,
    )
    return _serve(certificate.fichier_pdf, download=True)


@school_role_required(*STAFF_ROLES)
def issued_document_file(request, document_id):
    school = school_for_user(request.user)
    document = get_object_or_404(
        DocumentEmis, pk=document_id, ecole=school,
        etudiant__ecole=school, annee_scolaire__ecole=school,
    )
    return _serve(document.fichier_pdf, download=True)


@school_role_required(*STAFF_ROLES)
def school_asset(request, ecole_id, asset):
    school = school_for_user(request.user)
    if school.pk != ecole_id or asset not in {'cachet', 'signature'}:
        raise Http404('Fichier absent.')
    field = school.cachet_admin if asset == 'cachet' else school.signature_directeur
    return _serve(field)


def school_logo(request, ecole_id):
    school = get_object_or_404(EcoleSettings, pk=ecole_id)
    response = _serve(school.logo)
    response['Cache-Control'] = 'public, max-age=86400'
    return response
