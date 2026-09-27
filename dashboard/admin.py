# dashboard/admin.py
from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from .admin_site import site

site.register(User, UserAdmin)
site.register(Group, GroupAdmin)
from .models import (
    AnneeScolaire, Enseignant, Classe, Matiere, ProgrammeMatiere, Inscription,
    Etudiant, DossierInscriptionImage, Note, Paiement, CreanceScolaire, Presence,
    CertificatFrequentation, EcoleSettings , EmploiDuTemps , Profile, DemandeAbonnement,
    ModeleDocument, DocumentEmis, Evaluation, ResultatEvaluation, RegleBulletinAnnuel,
)


site.register(EcoleSettings)
site.register(Profile)


@admin.register(EmploiDuTemps, site=site)
class EmploiDuTempsAdmin(admin.ModelAdmin):
    list_display = ('classe', 'jour', 'heure_debut', 'heure_fin', 'matiere', 'enseignant', 'annee_scolaire')
    list_filter = ('classe', 'jour', 'enseignant', 'matiere', 'annee_scolaire')
    search_fields = ('classe__nom_classe', 'enseignant__nom', 'matiere__nom')

site.register(AnneeScolaire)
site.register(Enseignant)
site.register(Classe)
site.register(Matiere)
site.register(ProgrammeMatiere)
site.register(Etudiant)
site.register(DossierInscriptionImage)
@admin.register(Note, site=site)
class NoteAdmin(admin.ModelAdmin):
    """Les anciennes notes restent consultables ; la saisie passe par le parcours école."""

    list_display = ('etudiant', 'matiere', 'periode_evaluation', 'valeur', 'annee_scolaire', 'ecole')
    list_filter = ('ecole', 'annee_scolaire', 'periode_evaluation')
    search_fields = ('etudiant__nom', 'etudiant__prenom', 'matiere__nom')
    list_select_related = ('etudiant', 'matiere', 'annee_scolaire', 'ecole')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

site.register(Paiement)

@admin.register(CreanceScolaire, site=site)
class CreanceScolaireAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'ecole', 'annee_scolaire', 'motif', 'montant_du', 'a_verifier')
    list_filter = ('ecole', 'annee_scolaire', 'a_verifier')
    search_fields = ('etudiant__nom', 'etudiant__prenom', 'etudiant__numero_matricule')

site.register(Presence)
@admin.register(CertificatFrequentation, site=site)
class CertificatFrequentationAdmin(admin.ModelAdmin):
    """L'archive émise est figée ; l'administration peut uniquement la révoquer."""

    list_display = ('numero_certificat', 'ecole', 'etudiant', 'annee_scolaire', 'statut')
    list_filter = ('ecole', 'annee_scolaire', 'statut')
    search_fields = ('numero_certificat', 'etudiant__nom', 'etudiant__prenom')
    readonly_fields = (
        'ecole', 'etudiant', 'annee_scolaire', 'date_delivrance',
        'numero_certificat', 'lieu_delivrance', 'fichier_pdf', 'delivre_par',
        'cachet_utilise', 'signature_utilisee', 'ministere', 'academie',
        'etablissement_reference', 'adresse_etablissement', 'mention_legale',
        'qr_code', 'code_verification', 'created_at', 'updated_at',
    )

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.statut != 'valide':
            return (*fields, 'statut')
        return fields

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.action(description="Confirmer le paiement et activer 30 jours")
def confirmer_demandes_abonnement(modeladmin, request, queryset):
    from datetime import timedelta
    from django.db import transaction
    from django.utils import timezone

    for demande_id in queryset.values_list('pk', flat=True):
        with transaction.atomic():
            demande = DemandeAbonnement.objects.select_for_update().get(pk=demande_id)
            if demande.statut != 'pending':
                continue
            ecole = EcoleSettings.objects.select_for_update().get(pk=demande.ecole_id)
            now = timezone.now()
            demande.statut = 'paid'
            demande.confirme_le = now
            demande.save(update_fields=['statut', 'confirme_le'])
            base = max(ecole.date_fin_abonnement or now, now)
            ecole.date_fin_abonnement = base + timedelta(days=30)
            ecole.statut_abonnement = 'active'
            ecole.est_active = True
            ecole.save(update_fields=['date_fin_abonnement', 'statut_abonnement', 'est_active', 'date_mise_a_jour'])


@admin.register(DemandeAbonnement, site=site)
class DemandeAbonnementAdmin(admin.ModelAdmin):
    list_display = ('ecole', 'montant', 'statut', 'cree_le', 'confirme_le')
    list_filter = ('statut', 'cree_le')
    search_fields = ('ecole__nom_etablissement', 'reference')
    readonly_fields = ('cree_le', 'confirme_le')
    actions = [confirmer_demandes_abonnement]

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Inscription, site=site)
class InscriptionAdmin(admin.ModelAdmin):
    list_display = ('etudiant', 'ecole', 'annee_scolaire', 'classe', 'statut')
    list_filter = ('ecole', 'annee_scolaire', 'statut')
    search_fields = ('etudiant__nom', 'etudiant__prenom', 'etudiant__numero_matricule')


@admin.register(ModeleDocument, site=site)
class ModeleDocumentAdmin(admin.ModelAdmin):
    list_display = ('ecole', 'type_document', 'code', 'titre', 'actif', 'modifie_le')
    list_filter = ('ecole', 'type_document', 'actif')
    search_fields = ('titre', 'code', 'ecole__nom_etablissement')
    readonly_fields = ('cree_le', 'modifie_le')


@admin.register(DocumentEmis, site=site)
class DocumentEmisAdmin(admin.ModelAdmin):
    list_display = ('numero_document', 'ecole', 'etudiant', 'type_document', 'date_emission', 'statut')
    list_filter = ('ecole', 'type_document', 'statut')
    search_fields = ('numero_document', 'etudiant__nom', 'etudiant__prenom')
    readonly_fields = (
        'ecole', 'etudiant', 'annee_scolaire', 'inscription', 'modele',
        'type_document', 'numero_document', 'code_verification', 'fichier_pdf',
        'modele_snapshot', 'donnees_snapshot', 'emis_par', 'date_emission',
        'statut', 'annule_le', 'annule_par', 'motif_annulation',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Evaluation, site=site)
class EvaluationAdmin(admin.ModelAdmin):
    """Lecture transversale pour le support, sans saisie hors de l'école."""

    list_display = ('ecole', 'classe', 'matiere', 'titre', 'periode_evaluation', 'date_evaluation', 'bareme', 'poids')
    list_filter = ('ecole', 'periode_evaluation', 'date_evaluation')
    search_fields = ('titre', 'programme__classe__nom_classe', 'programme__matiere__nom', 'ecole__nom_etablissement')
    list_select_related = ('ecole', 'programme__classe', 'programme__matiere')

    @admin.display(description='Classe')
    def classe(self, obj):
        return obj.programme.classe

    @admin.display(description='Matière')
    def matiere(self, obj):
        return obj.programme.matiere

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResultatEvaluation, site=site)
class ResultatEvaluationAdmin(admin.ModelAdmin):
    """Historique consultable, corrigé uniquement depuis le parcours école."""

    list_display = ('ecole', 'evaluation', 'eleve', 'valeur', 'annule', 'saisi_par', 'modifie_le')
    list_filter = ('annule', 'evaluation__ecole', 'evaluation__periode_evaluation')
    search_fields = ('evaluation__titre', 'inscription__etudiant__nom', 'inscription__etudiant__prenom', 'inscription__etudiant__numero_matricule')
    list_select_related = ('evaluation__ecole', 'inscription__etudiant')

    @admin.display(description='École')
    def ecole(self, obj):
        return obj.evaluation.ecole

    @admin.display(description='Élève')
    def eleve(self, obj):
        return obj.inscription.etudiant

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RegleBulletinAnnuel, site=site)
class RegleBulletinAnnuelAdmin(admin.ModelAdmin):
    """Consulter la règle validée, créée et modifiée par la direction de l'école."""

    list_display = (
        'ecole', 'annee_scolaire', 'cycle', 'poids_trimestre_1',
        'poids_trimestre_2', 'poids_trimestre_3', 'valide_par', 'valide_le',
    )
    list_filter = ('ecole', 'annee_scolaire', 'cycle')
    list_select_related = ('ecole', 'annee_scolaire', 'valide_par')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
