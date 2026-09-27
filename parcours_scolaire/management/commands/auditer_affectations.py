"""Lister les inscriptions dont le pointeur de classe ne concorde pas avec l'historique."""

from django.core.management.base import BaseCommand
from django.db.models import Prefetch

from dashboard.models import Inscription
from parcours_scolaire.models import AffectationClasse


class Command(BaseCommand):
    help = "Signale les inscriptions et affectations de classe à vérifier après la reprise."

    def add_arguments(self, parser):
        parser.add_argument('--ecole', type=int, help="Identifiant de l'école à auditer")

    def handle(self, *args, **options):
        inscriptions = Inscription.objects.select_related(
            'classe', 'annee_scolaire', 'etudiant',
        ).prefetch_related(Prefetch(
            'affectations_classe',
            queryset=AffectationClasse.objects.filter(date_fin__isnull=True),
            to_attr='affectations_ouvertes',
        )).order_by('ecole_id', 'pk')
        if options['ecole'] is not None:
            inscriptions = inscriptions.filter(ecole_id=options['ecole'])
        anomalies = 0
        for inscription in inscriptions.iterator(chunk_size=500):
            codes = []
            classe = inscription.classe
            ouvertes = inscription.affectations_ouvertes
            if inscription.etudiant.ecole_id != inscription.ecole_id:
                codes.append('eleve_autre_ecole')
            if inscription.annee_scolaire.ecole_id != inscription.ecole_id:
                codes.append('annee_autre_ecole')
            if classe and classe.ecole_id != inscription.ecole_id:
                codes.append('classe_autre_ecole')
            if classe and classe.annee_scolaire_id != inscription.annee_scolaire_id:
                codes.append('classe_autre_annee')
            if inscription.date_inscription > inscription.annee_scolaire.date_fin:
                codes.append('inscription_apres_fin_annee')
            if inscription.statut == 'active' and classe is None:
                codes.append('inscription_active_sans_classe')
            if inscription.statut == 'active' and classe:
                if not ouvertes:
                    codes.append('affectation_ouverte_absente')
                elif len(ouvertes) != 1 or ouvertes[0].classe_id != classe.pk:
                    codes.append('affectation_classe_differente')
            elif ouvertes:
                codes.append(
                    'affectation_ouverte_sans_classe' if inscription.statut == 'active'
                    else 'affectation_ouverte_inactive'
                )
            if codes:
                anomalies += 1
                self.stdout.write(
                    f"inscription={inscription.pk} ecole={inscription.ecole_id} "
                    f"codes={','.join(codes)}"
                )
        self.stdout.write(f'Inscriptions à revoir : {anomalies}')
