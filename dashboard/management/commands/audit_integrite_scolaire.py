"""Compte les incohérences scolaires sans lire ni afficher de données personnelles.

Usage : python manage.py audit_integrite_scolaire
La commande ne fait que des SELECT et ne modifie aucune donnée.
"""

from django.core.management.base import BaseCommand
from decimal import Decimal

from django.db.models import DecimalField, Exists, F, OuterRef, Q, Sum, Value
from django.db.models.functions import Coalesce

from dashboard.models import (
    AnneeScolaire,
    Classe,
    CertificatFrequentation,
    CreanceScolaire,
    EmploiDuTemps,
    Inscription,
    Note,
    Paiement,
    Presence,
    ProgrammeMatiere,
)


class Command(BaseCommand):
    help = (
        "Affiche uniquement des comptes agrégés d'incohérences scolaires ; "
        "ne modifie aucune donnée."
    )

    def handle(self, *args, **options):
        inscriptions_notes = Inscription.objects.filter(
            ecole_id=OuterRef("ecole_id"),
            etudiant_id=OuterRef("etudiant_id"),
            annee_scolaire_id=OuterRef("annee_scolaire_id"),
        )
        programmes_notes = ProgrammeMatiere.objects.filter(
            ecole_id=OuterRef("ecole_id"),
            matiere_id=OuterRef("matiere_id"),
            classe__inscriptions__ecole_id=OuterRef("ecole_id"),
            classe__inscriptions__etudiant_id=OuterRef("etudiant_id"),
            classe__inscriptions__annee_scolaire_id=OuterRef("annee_scolaire_id"),
        )
        inscriptions_presences = Inscription.objects.filter(
            ecole_id=OuterRef("ecole_id"),
            etudiant_id=OuterRef("etudiant_id"),
            annee_scolaire_id=OuterRef("annee_scolaire_id"),
            classe_id=OuterRef("classe_id"),
        )
        programmes_edt = ProgrammeMatiere.objects.filter(
            ecole_id=OuterRef("ecole_id"),
            classe_id=OuterRef("classe_id"),
            matiere_id=OuterRef("matiere_id"),
        )
        cours_chevauchant_classe = EmploiDuTemps.objects.filter(
            pk__lt=OuterRef("pk"),
            classe_id=OuterRef("classe_id"),
            annee_scolaire_id=OuterRef("annee_scolaire_id"),
            jour=OuterRef("jour"),
            heure_debut__lt=OuterRef("heure_fin"),
            heure_fin__gt=OuterRef("heure_debut"),
        )
        cours_chevauchant_enseignant = EmploiDuTemps.objects.filter(
            pk__lt=OuterRef("pk"),
            enseignant_id=OuterRef("enseignant_id"),
            annee_scolaire_id=OuterRef("annee_scolaire_id"),
            jour=OuterRef("jour"),
            heure_debut__lt=OuterRef("heure_fin"),
            heure_fin__gt=OuterRef("heure_debut"),
        )

        sections = (
            (
                "Années, classes et inscriptions",
                (
                    (
                        "Années avec dates invalides",
                        AnneeScolaire.objects.filter(date_fin__lte=F("date_debut")).count(),
                    ),
                    (
                        "Classes rattachées à une année d'une autre école",
                        Classe.objects.exclude(ecole_id=F("annee_scolaire__ecole_id")).count(),
                    ),
                    (
                        "Inscriptions avec école, année ou classe incohérentes",
                        Inscription.objects.filter(
                            ~Q(ecole_id=F("etudiant__ecole_id"))
                            | ~Q(ecole_id=F("annee_scolaire__ecole_id"))
                            | (
                                Q(classe__isnull=False)
                                & (
                                    ~Q(ecole_id=F("classe__ecole_id"))
                                    | ~Q(annee_scolaire_id=F("classe__annee_scolaire_id"))
                                )
                            )
                        ).count(),
                    ),
                ),
            ),
            (
                "Notes et programme",
                (
                    (
                        "Notes liées à une autre école (élève, matière ou année)",
                        Note.objects.filter(
                            ~Q(ecole_id=F("etudiant__ecole_id"))
                            | ~Q(ecole_id=F("matiere__ecole_id"))
                            | ~Q(ecole_id=F("annee_scolaire__ecole_id"))
                        ).count(),
                    ),
                    (
                        "Notes sans inscription correspondante",
                        Note.objects.annotate(
                            inscription_trouvee=Exists(inscriptions_notes)
                        ).filter(inscription_trouvee=False).count(),
                    ),
                    (
                        "Notes hors programme de la classe inscrite",
                        Note.objects.annotate(
                            inscription_trouvee=Exists(inscriptions_notes),
                            programme_trouve=Exists(programmes_notes),
                        ).filter(
                            inscription_trouvee=True, programme_trouve=False
                        ).count(),
                    ),
                    (
                        "Notes datées hors de l'année scolaire",
                        Note.objects.filter(
                            Q(date_evaluation__lt=F("annee_scolaire__date_debut"))
                            | Q(date_evaluation__gt=F("annee_scolaire__date_fin"))
                        ).count(),
                    ),
                    (
                        "Programmes avec coefficient non positif",
                        ProgrammeMatiere.objects.filter(coefficient__lte=0).count(),
                    ),
                    (
                        "Programmes avec école/classe/matière/enseignant incohérents",
                        ProgrammeMatiere.objects.filter(
                            ~Q(ecole_id=F("classe__ecole_id"))
                            | ~Q(ecole_id=F("matiere__ecole_id"))
                            | (
                                Q(enseignant__isnull=False)
                                & ~Q(ecole_id=F("enseignant__ecole_id"))
                            )
                        ).count(),
                    ),
                ),
            ),
            (
                "Présences",
                (
                    (
                        "Présences avec école, année, classe ou matière incohérentes",
                        Presence.objects.filter(
                            ~Q(ecole_id=F("etudiant__ecole_id"))
                            | ~Q(ecole_id=F("classe__ecole_id"))
                            | ~Q(ecole_id=F("annee_scolaire__ecole_id"))
                            | ~Q(annee_scolaire_id=F("classe__annee_scolaire_id"))
                            | (
                                Q(matiere__isnull=False)
                                & ~Q(ecole_id=F("matiere__ecole_id"))
                            )
                        ).count(),
                    ),
                    (
                        "Présences sans inscription dans cette classe et année",
                        Presence.objects.annotate(
                            inscription_trouvee=Exists(inscriptions_presences)
                        ).filter(inscription_trouvee=False).count(),
                    ),
                    (
                        "Présences datées hors de l'année scolaire",
                        Presence.objects.filter(
                            Q(date__lt=F("annee_scolaire__date_debut"))
                            | Q(date__gt=F("annee_scolaire__date_fin"))
                        ).count(),
                    ),
                ),
            ),
            (
                "Finances scolaires",
                (
                    (
                        "Frais avec encaissements supérieurs au montant dû",
                        CreanceScolaire.objects.annotate(
                            encaisse=Coalesce(
                                Sum('paiements__montant', filter=Q(paiements__annule=False)),
                                Value(Decimal('0.00')),
                                output_field=DecimalField(max_digits=12, decimal_places=2),
                            ),
                        ).filter(encaisse__gt=F('montant_du')).count(),
                    ),
                    (
                        "Paiements actifs sans frais scolaire rapproché",
                        Paiement.objects.filter(annule=False, creance__isnull=True).count(),
                    ),
                ),
            ),
            (
                "Documents administratifs",
                (
                    (
                        "Certificats avec anciens en-têtes codés en dur",
                        CertificatFrequentation.objects.filter(
                            Q(ministere="MINISTÈRE DE L’ENSEIGNEMENT SUPÉRIEUR / ET DE LA RECHERCHE SCIENTIFIQUE")
                            | Q(etablissement_reference="Complexe Scolaire Privé de Banankabougou")
                            | Q(adresse_etablissement="Banankabougou, Bamako - Mali")
                        ).count(),
                    ),
                ),
            ),
            (
                "Emploi du temps",
                (
                    (
                        "Cours avec école, année, classe, matière ou enseignant incohérents",
                        EmploiDuTemps.objects.filter(
                            ~Q(ecole_id=F("classe__ecole_id"))
                            | ~Q(ecole_id=F("matiere__ecole_id"))
                            | ~Q(ecole_id=F("enseignant__ecole_id"))
                            | ~Q(ecole_id=F("annee_scolaire__ecole_id"))
                            | ~Q(annee_scolaire_id=F("classe__annee_scolaire_id"))
                        ).count(),
                    ),
                    (
                        "Cours sur une matière hors programme de la classe",
                        EmploiDuTemps.objects.annotate(
                            programme_trouve=Exists(programmes_edt)
                        ).filter(programme_trouve=False).count(),
                    ),
                    (
                        "Cours avec horaire invalide",
                        EmploiDuTemps.objects.filter(heure_fin__lte=F("heure_debut")).count(),
                    ),
                    (
                        "Cours en chevauchement pour une même classe",
                        EmploiDuTemps.objects.annotate(
                            conflit=Exists(cours_chevauchant_classe)
                        ).filter(conflit=True).count(),
                    ),
                    (
                        "Cours en chevauchement pour un même enseignant",
                        EmploiDuTemps.objects.annotate(
                            conflit=Exists(cours_chevauchant_enseignant)
                        ).filter(conflit=True).count(),
                    ),
                ),
            ),
        )

        self.stdout.write("Audit d'intégrité scolaire — comptes agrégés uniquement")
        for titre, controles in sections:
            self.stdout.write(f"\n{titre}")
            for libelle, nombre in controles:
                self.stdout.write(f"  {libelle} : {nombre}")
        self.stdout.write(
            "\nLes catégories peuvent se recouper. "
            "Un changement de classe non historisé peut expliquer certains écarts d'inscription. "
            "Aucune donnée n'a été modifiée."
        )
