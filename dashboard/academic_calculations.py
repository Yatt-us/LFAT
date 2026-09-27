"""Calculs des bulletins avec contrôle des données scolaires disponibles.

Les règles annuelles et les autres modes d'évaluation demanderont une politique
validée pour l'école et le cycle avant de pouvoir produire un bulletin officiel.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from .models import Evaluation, Note, ProgrammeMatiere, RegleBulletinAnnuel, ResultatEvaluation


TRIMESTRES = frozenset({'Trimestre 1', 'Trimestre 2', 'Trimestre 3'})


class BulletinCalculationError(ValueError):
    """Données ou règles insuffisantes pour émettre un bulletin fiable."""


def _moyenne_non_arrondie(notes_et_coefficients):
    """Calcule une moyenne /20, sans arrondir les étapes intermédiaires."""
    total_points = Decimal('0')
    total_coefficients = Decimal('0')
    for valeur, coefficient in notes_et_coefficients:
        valeur = Decimal(valeur)
        coefficient = Decimal(coefficient)
        if not valeur.is_finite() or not Decimal('0') <= valeur <= Decimal('20'):
            raise BulletinCalculationError('Une note du bulletin est hors de la plage 0 à 20.')
        if not coefficient.is_finite() or coefficient <= 0:
            raise BulletinCalculationError('Chaque matière du programme doit avoir un coefficient positif.')
        total_points += valeur * coefficient
        total_coefficients += coefficient
    if total_coefficients <= 0:
        raise BulletinCalculationError('Aucune note avec un poids ou coefficient valide ne permet le calcul du bulletin.')
    return total_points / total_coefficients


def moyenne_ponderee(notes_et_coefficients):
    """Arrondit une seule fois la moyenne pondérée en fin de calcul."""
    return _moyenne_non_arrondie(notes_et_coefficients).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )


def bulletin_trimestriel(inscription, periode):
    """Retourne les lignes et la moyenne si les matières sont entièrement notées.

    Pour chaque matière, les évaluations détaillées remplacent la note legacy.
    Les deux sources simultanées ou un résultat manquant bloquent l'émission.
    """
    if periode not in TRIMESTRES:
        raise BulletinCalculationError('La règle de calcul de cette période n’est pas configurée pour l’école.')
    if not inscription.classe_id:
        raise BulletinCalculationError('L’élève doit être inscrit dans une classe pour cette année.')
    if inscription.statut != 'active':
        raise BulletinCalculationError('L’inscription de l’élève doit être active.')
    if (
        inscription.etudiant.ecole_id != inscription.ecole_id
        or inscription.annee_scolaire.ecole_id != inscription.ecole_id
        or inscription.classe.ecole_id != inscription.ecole_id
        or inscription.classe.annee_scolaire_id != inscription.annee_scolaire_id
    ):
        raise BulletinCalculationError('L’inscription, la classe et l’année scolaire sont incohérentes.')
    from parcours_scolaire.models import AffectationClasse
    if AffectationClasse.objects.filter(inscription=inscription).count() > 1:
        raise BulletinCalculationError(
            'La classe de cet élève a changé pendant l’année. Le calcul d’un bulletin '
            'sur plusieurs programmes doit être validé par la direction.'
        )

    programmes = list(
        ProgrammeMatiere.objects.filter(ecole_id=inscription.ecole_id, classe_id=inscription.classe_id)
        .select_related('matiere').order_by('matiere__nom', 'pk')
    )
    if not programmes:
        raise BulletinCalculationError('Aucune matière n’est définie au programme de cette classe.')
    if any(programme.matiere.ecole_id != inscription.ecole_id for programme in programmes):
        raise BulletinCalculationError('Une matière du programme appartient à une autre école.')

    notes = list(
        Note.objects.filter(
            ecole_id=inscription.ecole_id,
            etudiant_id=inscription.etudiant_id,
            annee_scolaire_id=inscription.annee_scolaire_id,
            periode_evaluation=periode,
        ).select_related('matiere')
    )
    programme_ids = {programme.matiere_id for programme in programmes}
    hors_programme = [note.matiere.nom for note in notes if note.matiere_id not in programme_ids]
    if hors_programme:
        raise BulletinCalculationError(
            'Des notes ne correspondent pas au programme de la classe : '
            + ', '.join(sorted(hors_programme)) + '.'
        )
    notes_par_matiere = {note.matiere_id: note for note in notes}

    evaluations = list(
        Evaluation.objects.filter(programme__in=programmes, periode_evaluation=periode)
        .select_related('programme__matiere').order_by('date_evaluation', 'pk')
    )
    if any(evaluation.ecole_id != inscription.ecole_id for evaluation in evaluations):
        raise BulletinCalculationError('Une évaluation appartient à une autre école.')
    evaluations_par_matiere = defaultdict(list)
    for evaluation in evaluations:
        evaluations_par_matiere[evaluation.programme.matiere_id].append(evaluation)
    resultats = {
        resultat.evaluation_id: resultat
        for resultat in ResultatEvaluation.objects.filter(
            evaluation__in=evaluations, inscription=inscription, annule=False,
        )
    }

    moyennes_et_coefficients = []
    lignes = []
    for programme in programmes:
        matiere = programme.matiere
        note_legacy = notes_par_matiere.get(matiere.pk)
        epreuves = evaluations_par_matiere[matiere.pk]
        if note_legacy and epreuves:
            raise BulletinCalculationError(
                f'La matière {matiere.nom} possède à la fois une ancienne note et des évaluations '
                'pour cette période. Choisissez une source avant d’émettre le bulletin.'
            )
        if epreuves:
            manquantes = [epreuve.titre for epreuve in epreuves if epreuve.pk not in resultats]
            if manquantes:
                raise BulletinCalculationError(
                    f'Résultats manquants en {matiere.nom} pour : ' + ', '.join(manquantes) + '.'
                )
            valeurs = []
            sources = []
            for epreuve in epreuves:
                bareme = Decimal(epreuve.bareme)
                if not bareme.is_finite() or bareme <= 0:
                    raise BulletinCalculationError(f'Le barème de {epreuve.titre} doit être positif.')
                resultat = resultats[epreuve.pk]
                valeur_brute = Decimal(resultat.valeur)
                valeur_sur_20 = valeur_brute * Decimal('20') / bareme
                valeurs.append((valeur_sur_20, epreuve.poids))
                sources.append({
                    'evaluation_id': epreuve.pk,
                    'resultat_id': resultat.pk,
                    'valeur': str(resultat.valeur),
                    'bareme': str(epreuve.bareme),
                    'poids': str(epreuve.poids),
                })
            moyenne_matiere = _moyenne_non_arrondie(valeurs)
        elif note_legacy:
            moyenne_matiere = Decimal(note_legacy.valeur)
            sources = [{'note_legacy_id': note_legacy.pk, 'valeur': str(note_legacy.valeur)}]
        else:
            raise BulletinCalculationError(f'Bulletin incomplet : notes manquantes pour {matiere.nom}.')

        coefficient = Decimal(programme.coefficient)
        moyennes_et_coefficients.append((moyenne_matiere, coefficient))
        valeur_affichee = moyenne_matiere.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        lignes.append({
            'matiere': matiere.nom,
            'matiere_id': matiere.pk,
            'valeur': f'{valeur_affichee:.2f}',
            'valeur_brute': str(moyenne_matiere),
            'coefficient': programme.coefficient,
            'sources': sources,
        })

    moyenne = moyenne_ponderee(moyennes_et_coefficients)
    return lignes, f'{moyenne:.2f}'


def bulletin_annuel(inscription):
    """Calcule l'année selon la règle explicitement validée pour ce cycle.

    Un trimestre de poids nul est exclu. Chaque trimestre retenu doit être
    complet ; les moyennes intermédiaires ne sont pas arrondies.
    """
    if not inscription.classe_id:
        raise BulletinCalculationError('Une classe est nécessaire pour calculer le bulletin annuel.')
    cycle = inscription.classe.cycle_scolaire
    if cycle is None:
        raise BulletinCalculationError('Le cycle scolaire de cette classe est inconnu.')
    regle = RegleBulletinAnnuel.objects.filter(
        ecole_id=inscription.ecole_id,
        annee_scolaire_id=inscription.annee_scolaire_id,
        cycle=cycle,
        valide_par__isnull=False, valide_le__isnull=False,
    ).first()
    if regle is None:
        raise BulletinCalculationError(
            'Aucune règle de calcul annuelle validée pour ce cycle, cette école et cette année scolaire.'
        )
    poids_par_periode = (
        ('Trimestre 1', Decimal(regle.poids_trimestre_1)),
        ('Trimestre 2', Decimal(regle.poids_trimestre_2)),
        ('Trimestre 3', Decimal(regle.poids_trimestre_3)),
    )
    if any(not poids.is_finite() or poids < 0 for _, poids in poids_par_periode):
        raise BulletinCalculationError('La règle annuelle possède un poids invalide.')
    poids_retenus = [(periode, poids) for periode, poids in poids_par_periode if poids > 0]
    if not poids_retenus:
        raise BulletinCalculationError('La règle annuelle ne retient aucun trimestre.')
    if Note.objects.filter(
        ecole_id=inscription.ecole_id,
        etudiant_id=inscription.etudiant_id,
        annee_scolaire_id=inscription.annee_scolaire_id,
        periode_evaluation='Annuelle',
    ).exists():
        raise BulletinCalculationError(
            'Des notes annuelles anciennes existent pour cet élève : clarifiez cette source '
            'avant de publier un bulletin annuel calculé depuis les trimestres.'
        )
    total_poids = sum((poids for _, poids in poids_retenus), Decimal('0'))

    lignes_par_periode = {}
    for periode, _ in poids_retenus:
        lignes, _ = bulletin_trimestriel(inscription, periode)
        lignes_par_periode[periode] = {ligne['matiere_id']: ligne for ligne in lignes}
    matieres = list(lignes_par_periode[poids_retenus[0][0]].values())
    ids_attendus = {ligne['matiere_id'] for ligne in matieres}
    if any(set(lignes) != ids_attendus for lignes in lignes_par_periode.values()):
        raise BulletinCalculationError('Le programme des matières diffère selon les trimestres requis.')

    lignes_annuelles = []
    moyennes_et_coefficients = []
    for matiere in matieres:
        matiere_id = matiere['matiere_id']
        contributions = []
        sources = []
        for periode, poids in poids_retenus:
            trimestre = lignes_par_periode[periode][matiere_id]
            valeur_brute = Decimal(trimestre['valeur_brute'])
            contributions.append(valeur_brute * poids)
            sources.append({
                'periode': periode, 'poids': str(poids),
                'valeur_brute': trimestre['valeur_brute'],
                'evaluations_ou_note': trimestre['sources'],
            })
        valeur_annuelle = sum(contributions, Decimal('0')) / total_poids
        coefficient = matiere['coefficient']
        moyennes_et_coefficients.append((valeur_annuelle, coefficient))
        lignes_annuelles.append({
            'matiere': matiere['matiere'], 'matiere_id': matiere_id,
            'valeur': f"{valeur_annuelle.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}",
            'valeur_brute': str(valeur_annuelle),
            'coefficient': coefficient,
            'regle_bulletin_id': regle.pk,
            'regle_validee_le': regle.valide_le.isoformat(),
            'sources': sources,
        })
    moyenne = moyenne_ponderee(moyennes_et_coefficients)
    return lignes_annuelles, f'{moyenne:.2f}'


def determiner_mention_malienne(moyenne):
    """Détermine la mention officielle selon le barème du système éducatif malien."""
    val = Decimal(str(moyenne))
    if val >= Decimal('16.00'):
        return 'tres_bien'
    if val >= Decimal('14.00'):
        return 'bien'
    if val >= Decimal('12.00'):
        return 'assez_bien'
    if val >= Decimal('10.00'):
        return 'passable'
    if val >= Decimal('8.00'):
        return 'avertissement'
    return 'blame'


def recommander_decision_passage(moyenne_annuelle):
    """Recommande une décision officielle de passage ou d'orientation pour l'année."""
    val = Decimal(str(moyenne_annuelle))
    if val >= Decimal('10.00'):
        return 'admis'
    if val >= Decimal('9.00'):
        return 'conseil'
    return 'redouble'


def calculer_classement_classe(classe, periode):
    """Calcule les moyennes, les rangs (avec gestion des ex-aequo) et les statistiques d'une classe.
    
    Retourne :
      - 'classe': instance de Classe
      - 'periode': str
      - 'effectif': nombre d'élèves évalués
      - 'moyenne_classe': moyenne de la classe (Decimal à 2 décimales)
      - 'moyenne_max': plus forte moyenne (Decimal)
      - 'moyenne_min': plus faible moyenne (Decimal)
      - 'resultats': liste ordonnée des résultats par rang
      - 'erreurs': liste des dicts {'inscription', 'etudiant', 'erreur'}
    """
    from .models import Inscription

    inscriptions = Inscription.objects.filter(
        classe=classe,
        annee_scolaire=classe.annee_scolaire,
        statut='active',
    ).select_related('etudiant', 'classe', 'annee_scolaire', 'ecole').order_by('etudiant__nom', 'etudiant__prenom')

    succes = []
    erreurs = []

    for insc in inscriptions:
        try:
            if periode in {'Annuelle', 'Annuel'}:
                lignes, moyenne_str = bulletin_annuel(insc)
            else:
                lignes, moyenne_str = bulletin_trimestriel(insc, periode)
            moyenne_dec = Decimal(moyenne_str)
            succes.append({
                'inscription': insc,
                'moyenne': moyenne_dec,
                'bulletin_lignes': lignes,
            })
        except BulletinCalculationError as exc:
            erreurs.append({
                'inscription': insc,
                'etudiant': insc.etudiant,
                'erreur': str(exc),
            })
        except Exception as exc:
            erreurs.append({
                'inscription': insc,
                'etudiant': insc.etudiant,
                'erreur': str(exc),
            })

    succes.sort(key=lambda item: item['moyenne'], reverse=True)

    resultats_classes = []
    current_rank = 1
    for i, item in enumerate(succes):
        if i > 0:
            if item['moyenne'] < succes[i - 1]['moyenne']:
                current_rank = i + 1
        mention = determiner_mention_malienne(item['moyenne'])
        decision = recommander_decision_passage(item['moyenne']) if (periode in {'Annuelle', 'Annuel'}) else None
        resultats_classes.append({
            'inscription': item['inscription'],
            'moyenne': item['moyenne'],
            'rang': current_rank,
            'mention': mention,
            'decision_recommandee': decision,
            'bulletin_lignes': item['bulletin_lignes'],
        })

    effectif = len(resultats_classes)
    if effectif > 0:
        total_moyennes = sum((item['moyenne'] for item in resultats_classes), Decimal('0'))
        moyenne_classe = (total_moyennes / Decimal(effectif)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        moyenne_max = resultats_classes[0]['moyenne']
        moyenne_min = resultats_classes[-1]['moyenne']
    else:
        moyenne_classe = Decimal('0.00')
        moyenne_max = Decimal('0.00')
        moyenne_min = Decimal('0.00')

    return {
        'classe': classe,
        'periode': periode,
        'effectif': effectif,
        'moyenne_classe': moyenne_classe,
        'moyenne_max': moyenne_max,
        'moyenne_min': moyenne_min,
        'resultats': resultats_classes,
        'erreurs': erreurs,
    }
