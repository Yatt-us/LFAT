"""Text-only document layouts shared by every school.

The layout is saved in the database.  It is deliberately not a Django template:
only the named substitutions below are accepted, and no user supplied markup is
interpreted as HTML.
"""

import re
from collections.abc import Mapping

from django.core.exceptions import ValidationError
from django.utils.html import format_html, format_html_join


DOCUMENT_TYPES = (
    ("bulletin", "Bulletin de notes"),
    ("frequentation", "Certificat de fréquentation"),
    ("attestation_scolarite", "Attestation de scolarité"),
    ("certificat_inscription", "Certificat d’inscription"),
    ("autre", "Autre document administratif"),
)

ALLOWED_PLACEHOLDERS = frozenset(
    {
        "ecole_nom",
        "ecole_adresse",
        "ecole_telephone",
        "eleve_nom_complet",
        "eleve_nom",
        "eleve_prenom",
        "matricule",
        "classe",
        "annee_scolaire",
        "date_naissance",
        "lieu_naissance",
        "date_emission",
        "lieu_delivrance",
        "numero_document",
        "nom_signataire",
        "titre_signataire",
        "moyenne",
        "periode",
    }
)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_TEMPLATES = {
    "bulletin": {
        "titre": "BULLETIN DE NOTES",
        "entete": "{{ ecole_nom }}\nAnnée scolaire : {{ annee_scolaire }}",
        "corps": "Élève : {{ eleve_nom_complet }}\nMatricule : {{ matricule }}\nClasse : {{ classe }}",
        "mention": "",
        "pied_de_page": "Édité le {{ date_emission }}",
        "titre_signataire": "Le Directeur",
        "afficher_logo": True,
        "afficher_cachet": True,
        "afficher_signature": True,
    },
    "frequentation": {
        "titre": "CERTIFICAT DE FRÉQUENTATION",
        "entete": "{{ ecole_nom }}",
        "corps": (
            "Je soussigné(e), {{ titre_signataire }}, certifie que "
            "{{ eleve_nom_complet }}, matricule {{ matricule }}, fréquente "
            "régulièrement la classe de {{ classe }} au titre de l’année "
            "scolaire {{ annee_scolaire }}."
        ),
        "mention": "Le présent certificat est délivré pour servir et valoir ce que de droit.",
        "pied_de_page": "Fait à {{ lieu_delivrance }}, le {{ date_emission }}",
        "titre_signataire": "Le Directeur",
        "afficher_logo": True,
        "afficher_cachet": True,
        "afficher_signature": True,
    },
    "attestation_scolarite": {
        "titre": "ATTESTATION DE SCOLARITÉ",
        "entete": "{{ ecole_nom }}",
        "corps": (
            "Je soussigné(e), {{ titre_signataire }}, atteste que "
            "{{ eleve_nom_complet }}, matricule {{ matricule }}, est "
            "scolarisé(e) dans notre établissement, en classe de {{ classe }}, "
            "pour l’année scolaire {{ annee_scolaire }}."
        ),
        "mention": "La présente attestation est délivrée pour servir et valoir ce que de droit.",
        "pied_de_page": "Fait à {{ lieu_delivrance }}, le {{ date_emission }}",
        "titre_signataire": "Le Directeur",
        "afficher_logo": True,
        "afficher_cachet": True,
        "afficher_signature": True,
    },
    "certificat_inscription": {
        "titre": "CERTIFICAT D’INSCRIPTION",
        "entete": "{{ ecole_nom }}",
        "corps": (
            "Je soussigné(e), {{ titre_signataire }}, certifie que "
            "{{ eleve_nom_complet }}, matricule {{ matricule }}, est "
            "inscrit(e) dans notre établissement en classe de {{ classe }} "
            "pour l’année scolaire {{ annee_scolaire }}."
        ),
        "mention": "Le présent certificat est délivré pour servir et valoir ce que de droit.",
        "pied_de_page": "Fait à {{ lieu_delivrance }}, le {{ date_emission }}",
        "titre_signataire": "Le Directeur",
        "afficher_logo": True,
        "afficher_cachet": True,
        "afficher_signature": True,
    },
    "autre": {
        "titre": "DOCUMENT ADMINISTRATIF",
        "entete": "{{ ecole_nom }}",
        "corps": "Concernant {{ eleve_nom_complet }}, classe de {{ classe }}, année scolaire {{ annee_scolaire }}.",
        "mention": "",
        "pied_de_page": "Fait à {{ lieu_delivrance }}, le {{ date_emission }}",
        "titre_signataire": "Le Directeur",
        "afficher_logo": True,
        "afficher_cachet": True,
        "afficher_signature": True,
    },
}


def default_document_fields(type_document: str) -> dict:
    """Return an independent copy so editing one school cannot change defaults."""
    try:
        return DEFAULT_TEMPLATES[type_document].copy()
    except KeyError as exc:
        raise ValueError("Type de document inconnu.") from exc


def validate_document_text(texte: str) -> None:
    """Reject markup, template logic, malformed tokens and unknown variables."""
    if not isinstance(texte, str):
        raise ValidationError("Le contenu du modèle doit être du texte.")
    if "<" in texte or ">" in texte or "{%" in texte or "%}" in texte:
        raise ValidationError("Le HTML et les instructions de modèle ne sont pas autorisés.")
    if _CONTROL.search(texte):
        raise ValidationError("Le texte contient des caractères de contrôle interdits.")
    unknown = {match.group(1) for match in _PLACEHOLDER.finditer(texte)} - ALLOWED_PLACEHOLDERS
    if unknown:
        raise ValidationError("Variable inconnue : %(variables)s", params={"variables": ", ".join(sorted(unknown))})
    remainder = _PLACEHOLDER.sub("", texte)
    if "{{" in remainder or "}}" in remainder:
        raise ValidationError("La syntaxe d’une variable est incorrecte.")


def render_document_text(texte: str, valeurs: Mapping[str, object]) -> str:
    """Substitute whitelisted variables and return plain text, never HTML."""
    validate_document_text(texte)
    if not isinstance(valeurs, Mapping):
        raise TypeError("Les valeurs doivent être une correspondance.")

    def replace(match):
        value = valeurs.get(match.group(1), "")
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(replace, texte)


def render_document_html(texte: str, valeurs: Mapping[str, object]):
    """HTML-safe preview with line breaks; suitable for Django templates."""
    lines = render_document_text(texte, valeurs).splitlines() or [""]
    return format_html_join(format_html("<br>"), "{}", ((line,) for line in lines))
