"""Point d’entrée public des vues du dashboard.

Les URL historiques importent toujours leurs vues depuis ``dashboard.views``.
L’implémentation est répartie par domaine dans ce package.
"""

from .core import initier_paiement, recherche_etudiants, dashboard_accueil, config_ecole_view
from .students import liste_etudiants, creer_etudiant, detail_etudiant, inscrire_etudiant, modifier_etudiant, supprimer_etudiant
from .school_years import liste_annees_scolaires, creer_annee_scolaire, modifier_annee_scolaire, supprimer_annee_scolaire, activer_annee_scolaire
from .classes import liste_classes, creer_classe, modifier_classe, supprimer_classe
from .staff import liste_enseignants, creer_enseignant, modifier_enseignant, supprimer_enseignant
from .subjects import liste_matieres, creer_matiere, modifier_matiere, supprimer_matiere, liste_programmes_matiere, creer_programme_matiere, modifier_programme_matiere, supprimer_programme_matiere
from .notes import ajouter_note, saisir_notes_classe_matiere, modifier_note, supprimer_note, liste_notes_par_classe, export_notes_excel, import_notes_excel
from .evaluations import liste_evaluations, creer_evaluation, saisir_resultats_evaluation
from .payments import liste_paiements_par_classe_etudiant, liste_paiements_impayes, liste_paiements_payes, generer_recu_paiement, creer_creance_scolaire, modifier_creance_scolaire, ajouter_paiement, modifier_paiement, supprimer_paiement
from .attendance import marquer_presence_classe, liste_presences, suivi_presence_classe, suivi_presence_eleve
from .timetables import liste_emplois_du_temps, creer_emploi_du_temps, creer_emploi_du_temps_pour_classe, modifier_emploi_du_temps, modifier_emploi_du_temps_classe
from .documents import (
    generer_certificat_frequentation, creer_certificat_interface, generer_bulletin_scolaire,
    carte_scolaire, verifier_etudiant, verification_carte_scolaire, verifier_certificat,
    generer_attestation_scolarite, generer_certificat_inscription, generer_document_personnalise,
    verifier_document, annuler_document_emis, generer_bulletins_classe_vue, telecharger_bulletins_zip_vue,
)
from .common import get_user_ecole
from .document_templates import modeles_documents, creer_modele_document, modifier_modele_document, modifier_modele_document_libre
