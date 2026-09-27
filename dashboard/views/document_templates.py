"""Configuration persistante des documents propres à chaque école."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from ..access import school_role_required
from ..document_templates import ALLOWED_PLACEHOLDERS, default_document_fields, render_document_text
from ..forms import ModeleDocumentForm
from ..models import EcoleSettings, ModeleDocument
from ..tenant import school_for_user


STANDARD_TYPES = (
    ModeleDocument.TYPE_BULLETIN,
    ModeleDocument.TYPE_FREQUENTATION,
    ModeleDocument.TYPE_ATTESTATION,
    ModeleDocument.TYPE_INSCRIPTION,
)
PREVIEW_FIELDS = (
    'titre', 'entete', 'corps', 'pied_de_page', 'mention', 'titre_signataire',
)


def _preview_values(ecole, modele):
    """Données fictives affichées clairement comme exemple à l'écran."""
    return {
        'ecole_nom': ecole.nom_etablissement,
        'ecole_adresse': ecole.adresse_etablissement or '',
        'ecole_telephone': ecole.telephone or '',
        'eleve_nom_complet': 'Aïssata Traoré',
        'eleve_nom': 'Traoré',
        'eleve_prenom': 'Aïssata',
        'matricule': 'EXEMPLE-001',
        'classe': '6e A',
        'annee_scolaire': '2026-2027',
        'date_naissance': '15/03/2013',
        'lieu_naissance': 'Bamako',
        'date_emission': timezone.localdate().strftime('%d/%m/%Y'),
        'lieu_delivrance': ecole.commune or 'Bamako',
        'numero_document': 'EXEMPLE-2026-001',
        'nom_signataire': ecole.nom_signataire or 'Nom du signataire',
        'titre_signataire': modele.titre_signataire or ecole.titre_signataire or 'La direction',
        'moyenne': '14,5/20',
        'periode': 'Trimestre 1',
    }


def _preview(modele, ecole):
    values = _preview_values(ecole, modele)
    preview = {}
    for field in PREVIEW_FIELDS:
        try:
            preview[field] = render_document_text(getattr(modele, field) or '', values)
        except ValidationError:
            preview[field] = 'Corrigez ce champ pour afficher son aperçu.'
    return preview


def _code_disponible(ecole, titre):
    """Construit un identifiant stable pour un nouveau modèle libre."""
    base = slugify((titre or '')[:180])[:64].strip('-') or 'document'
    code = base
    suffix = 2
    while ModeleDocument.objects.filter(
        ecole=ecole, type_document=ModeleDocument.TYPE_AUTRE, code=code,
    ).exists():
        ending = f'-{suffix}'
        code = f'{base[:80 - len(ending)]}{ending}'
        suffix += 1
    return code


def _new_custom(ecole):
    return ModeleDocument(
        ecole=ecole,
        type_document=ModeleDocument.TYPE_AUTRE,
        code='nouveau-document',
        **default_document_fields(ModeleDocument.TYPE_AUTRE),
    )


def _editor(request, ecole, modele, *, nouveau=False):
    """Valide sur le serveur, puis enregistre uniquement sur action explicite."""
    form = ModeleDocumentForm(instance=modele)
    apercu_modele = modele
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'enregistrer':
            # Le verrou de l'école sérialise les créations simultanées de plans.
            with transaction.atomic():
                ecole = EcoleSettings.objects.select_for_update().get(pk=ecole.pk)
                if nouveau:
                    instance = _new_custom(ecole)
                    instance.code = _code_disponible(ecole, request.POST.get('titre', ''))
                elif modele.type_document == ModeleDocument.TYPE_AUTRE:
                    instance = get_object_or_404(
                        ModeleDocument, pk=modele.pk, ecole=ecole,
                        type_document=ModeleDocument.TYPE_AUTRE,
                    )
                else:
                    instance = ModeleDocument.pour_ecole(ecole, modele.type_document)
                form = ModeleDocumentForm(request.POST, instance=instance)
                if form.is_valid():
                    saved = form.save(commit=False)
                    saved.ecole = ecole
                    saved.type_document = instance.type_document
                    saved.code = instance.code
                    saved.save()
                    messages.success(
                        request,
                        'Le modèle est enregistré et sera utilisé pour les prochains documents.',
                    )
                    if saved.type_document == ModeleDocument.TYPE_AUTRE:
                        return redirect('modifier_modele_document_libre', pk=saved.pk)
                    return redirect('modifier_modele_document', type_document=saved.type_document)
                apercu_modele = instance
        elif action == 'apercu':
            instance = modele
            if nouveau:
                instance.code = _code_disponible(ecole, request.POST.get('titre', ''))
            form = ModeleDocumentForm(request.POST, instance=instance)
            if form.is_valid():
                apercu_modele = form.save(commit=False)
        else:
            raise Http404('Action inconnue.')

    return render(request, 'dashboard/documents/modeles_form.html', {
        'form': form,
        'ecole': ecole,
        'modele': modele,
        'type_document': modele.type_document,
        'type_libelle': modele.get_type_document_display(),
        'nouveau': nouveau,
        'personnalise': modele.type_document == ModeleDocument.TYPE_AUTRE,
        'plan_enregistre': bool(modele.pk),
        'apercu': _preview(apercu_modele, ecole),
        'afficher_logo': apercu_modele.afficher_logo,
        'afficher_cachet': apercu_modele.afficher_cachet,
        'afficher_signature': apercu_modele.afficher_signature,
        'variables_disponibles': sorted(ALLOWED_PLACEHOLDERS),
    })


@school_role_required('school_admin', 'director')
def modeles_documents(request):
    ecole = school_for_user(request.user)
    standards = [
        {'type': type_document, 'modele': modele, 'enregistre': bool(modele.pk)}
        for type_document in STANDARD_TYPES
        for modele in [ModeleDocument.pour_ecole(ecole, type_document)]
    ]
    libres = ModeleDocument.objects.filter(
        ecole=ecole, type_document=ModeleDocument.TYPE_AUTRE,
    ).order_by('titre', 'pk')
    return render(request, 'dashboard/documents/modeles_liste.html', {
        'standards': standards,
        'libres': libres,
    })


@school_role_required('school_admin', 'director')
def modifier_modele_document(request, type_document):
    if type_document not in STANDARD_TYPES:
        raise Http404('Type de document inconnu.')
    ecole = school_for_user(request.user)
    modele = ModeleDocument.pour_ecole(ecole, type_document)
    return _editor(request, ecole, modele)


@school_role_required('school_admin', 'director')
def creer_modele_document(request):
    ecole = school_for_user(request.user)
    return _editor(request, ecole, _new_custom(ecole), nouveau=True)


@school_role_required('school_admin', 'director')
def modifier_modele_document_libre(request, pk):
    ecole = school_for_user(request.user)
    modele = get_object_or_404(
        ModeleDocument, pk=pk, ecole=ecole,
        type_document=ModeleDocument.TYPE_AUTRE,
    )
    return _editor(request, ecole, modele)
