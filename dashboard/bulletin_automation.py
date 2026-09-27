"""Service d'automatisation et de génération en masse des bulletins scolaires.

Permet de :
- Calculer les moyennes et classements pour toute une classe (avec rangs et mentions maliennes)
- Enregistrer automatiquement les décisions du conseil de classe
- Émettre et archiver les bulletins officiels (PDF avec QR code de vérification)
- Notifier instantanément les parents/tuteurs (SMS / WhatsApp)
- Assembler tous les bulletins de la classe dans une archive ZIP prête pour impression
"""

import io
import json
import zipfile
from decimal import Decimal
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .academic_calculations import (
    BulletinCalculationError,
    bulletin_annuel,
    bulletin_trimestriel,
    calculer_classement_classe,
)
from .models import (
    Classe,
    DecisionConseilClasse,
    DocumentEmis,
    ModeleDocument,
    NotificationParent,
)


def emettre_document_bulletin(request, modele, etudiant, inscription, periode, notes, moyenne, user):
    """Génère et archive un bulletin officiel avec son code de vérification et PDF."""
    from .views.documents import _document_fingerprint, _document_values, _render_configured_pdf

    ecole = inscription.ecole
    rows = notes or []
    fingerprint = _document_fingerprint(
        modele, ecole, etudiant, inscription, periode=periode, notes=rows, moyenne=moyenne,
    )

    with transaction.atomic():
        # Annule les anciens bulletins de la même période pour éviter les doublons
        DocumentEmis.objects.filter(
            ecole=ecole,
            etudiant=etudiant,
            annee_scolaire=inscription.annee_scolaire,
            inscription=inscription,
            type_document=ModeleDocument.TYPE_BULLETIN,
            statut=DocumentEmis.STATUT_VALIDE,
            donnees_snapshot__periode=periode,
        ).update(
            statut=DocumentEmis.STATUT_ANNULE,
            annule_le=timezone.now(),
            annule_par=user,
            motif_annulation='Remplacé par la génération automatisée du bulletin.',
        )

        document = DocumentEmis(
            ecole=ecole,
            etudiant=etudiant,
            annee_scolaire=inscription.annee_scolaire,
            inscription=inscription,
            emis_par=user,
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
        if request:
            verification_url = request.build_absolute_uri(
                reverse('verifier_document', args=[document.code_verification])
            )
        else:
            verification_url = reverse('verifier_document', args=[document.code_verification])

        pdf_data = _render_configured_pdf(
            request, modele, ecole, values, notes=rows, qr_url=verification_url,
        )
        document.donnees_snapshot = {
            **values, 'empreinte': fingerprint, 'notes': rows,
        }
        filename = f"{modele.type_document}_{document.numero_document}.pdf"
        document.fichier_pdf.save(filename, ContentFile(pdf_data), save=False)
        document.save(update_fields=['donnees_snapshot', 'fichier_pdf'])

    return document


def automatiser_bulletins_classe(request, classe, periode, user=None, notifier_parents=False):
    """Génère en masse les bulletins pour toute une classe avec calcul des rangs et mentions.

    Retourne un dictionnaire avec :
      - 'succes': liste des dicts {'inscription', 'etudiant', 'document', 'decision'}
      - 'erreurs': liste des dicts {'inscription', 'etudiant', 'erreur'}
      - 'statistiques': moyennes de classe, effectif, etc.
    """
    ecole = classe.ecole
    modele = ModeleDocument.pour_ecole(ecole, ModeleDocument.TYPE_BULLETIN)
    if not modele.actif:
        raise ValueError("Le modèle de bulletin est actuellement désactivé pour cette école.")

    classement = calculer_classement_classe(classe, periode)
    resultats_succes = []
    erreurs = list(classement.get('erreurs', []))

    for item in classement.get('resultats', []):
        insc = item['inscription']
        etudiant = insc.etudiant
        moyenne_val = item['moyenne']
        moyenne_str = f"{moyenne_val:.2f}"
        rang = item['rang']
        mention = item['mention']
        decision_recommandee = item.get('decision_recommandee')
        notes_lignes = item['bulletin_lignes']

        try:
            # 1. Émission et archivage du PDF officiel
            document = emettre_document_bulletin(
                request, modele, etudiant, insc, periode, notes_lignes, moyenne_str, user,
            )

            # 2. Enregistrement officiel de la décision du conseil de classe
            decision, _ = DecisionConseilClasse.objects.update_or_create(
                inscription=insc,
                periode=periode,
                defaults={
                    'ecole': ecole,
                    'moyenne': moyenne_val,
                    'rang': rang,
                    'effectif': classement['effectif'],
                    'moyenne_classe': classement['moyenne_classe'],
                    'moyenne_max': classement['moyenne_max'],
                    'moyenne_min': classement['moyenne_min'],
                    'mention': mention,
                    'decision_passage': decision_recommandee or 'en_attente',
                    'valide_par': user,
                    'date_validation': timezone.now(),
                },
            )

            # 3. Notification automatique aux parents si activée
            if notifier_parents:
                contact = etudiant.get_contact_urgence() or etudiant.get_responsable_financier()
                destinataire = contact.telephone_principal if contact else etudiant.contact_parent
                if destinataire:
                    mention_texte = f", Mention : {decision.get_mention_display()}" if mention else ""
                    msg = (
                        f"{ecole.nom_etablissement} : Le bulletin du {periode} de votre enfant "
                        f"{etudiant.prenom} {etudiant.nom} est disponible. "
                        f"Moyenne : {moyenne_str}/20 (Rang : {rang}e/{classement['effectif']}{mention_texte})."
                    )
                    NotificationParent.objects.create(
                        ecole=ecole,
                        tuteur=contact,
                        etudiant=etudiant,
                        type_evenement='bulletin',
                        canal=contact.canal_prefere if contact and contact.canal_prefere in {'sms', 'whatsapp'} else 'sms',
                        destinataire=destinataire,
                        message=msg,
                        statut='envoye',
                        reference_externe=f"BULL-{document.numero_document}",
                        declenche_par=user,
                    )

            resultats_succes.append({
                'inscription': insc,
                'etudiant': etudiant,
                'document': document,
                'decision': decision,
                'moyenne': moyenne_str,
                'rang': rang,
                'mention': mention,
            })
        except Exception as exc:
            erreurs.append({
                'inscription': insc,
                'etudiant': etudiant,
                'erreur': str(exc),
            })

    return {
        'succes': resultats_succes,
        'erreurs': erreurs,
        'effectif': classement.get('effectif', 0),
        'moyenne_classe': classement.get('moyenne_classe', Decimal('0.00')),
        'moyenne_max': classement.get('moyenne_max', Decimal('0.00')),
        'moyenne_min': classement.get('moyenne_min', Decimal('0.00')),
    }


def creer_zip_bulletins_classe(classe, periode):
    """Rassemble tous les bulletins PDF actifs d'une classe et d'une période dans une archive ZIP."""
    documents = DocumentEmis.objects.filter(
        ecole=classe.ecole,
        inscription__classe=classe,
        annee_scolaire=classe.annee_scolaire,
        type_document=ModeleDocument.TYPE_BULLETIN,
        statut=DocumentEmis.STATUT_VALIDE,
        donnees_snapshot__periode=periode,
    ).select_related('etudiant')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for doc in documents:
            if doc.fichier_pdf and doc.fichier_pdf.storage.exists(doc.fichier_pdf.name):
                nom_eleve = f"{doc.etudiant.nom}_{doc.etudiant.prenom}".replace(" ", "_")
                nom_fichier = f"Bulletin_{nom_eleve}_{doc.numero_document}.pdf"
                with doc.fichier_pdf.open('rb') as f:
                    zip_file.writestr(nom_fichier, f.read())

    buffer.seek(0)
    return buffer
