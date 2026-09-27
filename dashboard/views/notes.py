"""Vues notes du tableau de bord."""

from .common import *
from ..access import school_role_required, teacher_can_teach, assigned_programs, is_teacher_account
from django.utils.dateparse import parse_date
from decimal import Decimal, InvalidOperation
from ..models import Evaluation


PERIODES_NOTES_SAISISSABLES = ('Trimestre 1', 'Trimestre 2', 'Trimestre 3')
MESSAGE_NOTE_ANNUELLE = (
    "La saisie directe d'une note annuelle est fermée : le bulletin annuel est calculé "
    "à partir des trimestres selon la règle validée par l'école pour ce cycle."
)


@school_role_required('school_admin', 'director', 'teacher')
def ajouter_note(request, etudiant_id):
    """
    Ajouter une note pour un étudiant spécifique, en respectant l'école de l'utilisateur.
    Gestion de l'année scolaire active pour éviter MultipleObjectsReturned.
    """

    # 1️⃣ Récupération de l'école de l'utilisateur via profil
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 2️⃣ Récupération de l'étudiant et vérification qu'il appartient à la même école
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)

    # 3️⃣ Récupération de l'année scolaire active pour l'école
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.error(request, "Aucune année scolaire active n'a été trouvée pour votre école.")
        return redirect('liste_annees_scolaires')

    inscription = etudiant.inscriptions.filter(ecole=ecole, annee_scolaire=annee_active, statut='active').select_related('classe').first()
    if not inscription or not inscription.classe_id:
        return HttpResponse("Cet élève n'est pas inscrit dans une classe pour l'année active.", status=400)
    if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, inscription.classe_id, year=annee_active):
        return HttpResponse('Vous n’êtes pas affecté à la classe de cet élève.', status=403)

    # 4️⃣ Traitement du formulaire
    if request.method == 'POST':
        if request.POST.get('periode_evaluation') == 'Annuelle':
            return HttpResponse(MESSAGE_NOTE_ANNUELLE, status=409)
        form = NoteForm(request.POST, ecole=ecole, annee_scolaire=annee_active, classe=inscription.classe if inscription else None, user=request.user)
        if form.is_valid():
            note = form.save(commit=False)
            note.etudiant = etudiant
            note.ecole = ecole
            note.annee_scolaire = annee_active
            if not ProgrammeMatiere.objects.filter(ecole=ecole, classe=inscription.classe, matiere=note.matiere).exists():
                form.add_error('matiere', "Cette matière n'est pas au programme de la classe.")
            elif Evaluation.objects.filter(
                ecole=ecole, programme__classe=inscription.classe,
                programme__matiere=note.matiere,
                periode_evaluation=note.periode_evaluation,
            ).exists():
                form.add_error('matiere', 'Des évaluations détaillées existent pour cette matière et cette période. Utilisez leur saisie.')
            else:
                note.save()
                messages.success(request, f"La note pour {etudiant.prenom} {etudiant.nom} a été ajoutée avec succès.")
                return redirect('detail_etudiant', etudiant_id=etudiant.pk)
        if form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field} : {error}")
    else:
        form = NoteForm(ecole=ecole, annee_scolaire=annee_active, classe=inscription.classe if inscription else None, user=request.user)

    # 5️⃣ Rendu du template
    return render(request, 'dashboard/etudiants/ajouter_note.html', {
        'form': form,
        'etudiant': etudiant,
        'annee_active': annee_active,
    })


# ... créer modifier_note, supprimer_note, ajouter_paiement, modifier_paiement, etc. sur le même principe

# --- Génération de Certificat de Fréquentation ---


@school_role_required('school_admin', 'director', 'teacher')
def modifier_note(request, pk):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    note = get_object_or_404(Note.objects.select_related('etudiant', 'matiere'), pk=pk, ecole=ecole)
    if note.periode_evaluation == 'Annuelle':
        return HttpResponse(
            'Cette note annuelle historique est conservée en lecture seule. ' + MESSAGE_NOTE_ANNUELLE,
            status=409,
        )
    inscription = note.etudiant.inscriptions.filter(annee_scolaire=note.annee_scolaire, statut='active').select_related('classe').first()
    if is_teacher_account(request.user) and (not inscription or not teacher_can_teach(request.user, ecole, inscription.classe_id, note.matiere_id, note.annee_scolaire)):
        return HttpResponse('Vous n’êtes pas affecté à cette matière.', status=403)

    if request.method == 'POST':
        try:
            nouvelle_valeur = Decimal(request.POST.get('valeur', '').strip().replace(',', '.'))
            if nouvelle_valeur < 0 or nouvelle_valeur > 20:
                raise ValueError('La note doit être entre 0 et 20.')
            note.valeur = nouvelle_valeur
            note.type_evaluation = request.POST.get('type_evaluation')
            parsed_date = parse_date(request.POST.get('date_evaluation', ''))
            if parsed_date is None:
                raise ValueError('La date est invalide.')
            note.date_evaluation = parsed_date
            note.save()
            messages.success(request, f"Note de {note.etudiant.prenom} {note.etudiant.nom} mise à jour.")
            if inscription and inscription.classe_id:
                return redirect('notes_par_classe_matiere',
                                classe_id=inscription.classe_id, matiere_id=note.matiere_id)
            return redirect('liste_notes_par_classe_matiere')
        except (ValueError, InvalidOperation) as e:
            messages.error(request, str(e) or "La valeur de la note doit être un nombre valide.")
        except Exception as e:
            messages.error(request, f"Erreur lors de la modification : {e}")

    return render(request, 'dashboard/notes/modifier_note.html', {'note': note})


# ======================================================
# Suppression individuelle d'une note
# ======================================================


@school_role_required('school_admin', 'director')
def supprimer_note(request, pk):
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    note = get_object_or_404(Note, pk=pk, ecole=ecole)
    if note.periode_evaluation == 'Annuelle':
        return HttpResponse(
            'Cette note annuelle historique est conservée en lecture seule. ' + MESSAGE_NOTE_ANNUELLE,
            status=409,
        )
    inscription = Inscription.objects.filter(
        etudiant=note.etudiant, annee_scolaire=note.annee_scolaire, ecole=ecole,
    ).first()
    classe_id = inscription.classe_id if inscription else None
    matiere_id = note.matiere_id

    if request.method == 'POST':
        note.delete()
        messages.success(request, f"Note de {note.etudiant.prenom} {note.etudiant.nom} supprimée.")
        if classe_id:
            return redirect('notes_par_classe_matiere', classe_id=classe_id, matiere_id=matiere_id)
        return redirect('liste_notes_par_classe_matiere')

    return render(request, 'dashboard/notes/confirmer_suppression_note.html', {'note': note})


# ======================================================
# Génération PDF du bulletin scolaire
# ======================================================


@school_role_required('school_admin', 'director', 'teacher')
def saisir_notes_classe_matiere(request, classe_id, matiere_id):
    """
    Saisie ou modification des notes pour une classe et une matière,
    filtrée par l'école de l'utilisateur connecté.
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole)
    matiere = get_object_or_404(Matiere, pk=matiere_id, ecole=ecole)

    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.error(request, "Veuillez définir une année scolaire active pour votre école.")
        return redirect('notes_par_classe_matiere', classe_id=classe_id, matiere_id=matiere_id)
    if classe.annee_scolaire_id != annee_active.pk:
        return HttpResponse("Cette classe n'appartient pas à l'année active.", status=400)
    if not ProgrammeMatiere.objects.filter(ecole=ecole, classe=classe, matiere=matiere).exists():
        return HttpResponse("Cette matière n'est pas au programme de la classe.", status=400)
    if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, classe.pk, matiere.pk, annee_active):
        return HttpResponse('Vous n’êtes pas affecté à cette matière.', status=403)

    etudiants = Etudiant.objects.filter(
        ecole=ecole, inscriptions__classe=classe, inscriptions__annee_scolaire=annee_active,
        inscriptions__statut='active'
    ).order_by('nom', 'prenom')
    periode_selectionnee = request.POST.get('periode_evaluation') or request.GET.get('periode_evaluation') or 'Trimestre 1'
    if periode_selectionnee not in PERIODES_NOTES_SAISISSABLES:
        periode_selectionnee = 'Trimestre 1'
    notes_existantes = {
        note.etudiant_id: note
        for note in Note.objects.filter(
            etudiant__in=etudiants,
            matiere=matiere,
            annee_scolaire=annee_active,
            periode_evaluation=periode_selectionnee,
            ecole=ecole
        )
    }

    if request.method == 'POST':
        periode = request.POST.get('periode_evaluation')
        type_eval = request.POST.get('type_evaluation')
        date_eval = request.POST.get('date_evaluation')

        if periode == 'Annuelle':
            return HttpResponse(MESSAGE_NOTE_ANNUELLE, status=409)
        parsed_date = parse_date(date_eval or '')
        if periode not in PERIODES_NOTES_SAISISSABLES or parsed_date is None:
            messages.error(request, 'La période ou la date de saisie est invalide.')
            return render(request, 'dashboard/notes/saisir_notes.html', {
                'classe': classe, 'matiere': matiere, 'annee_active': annee_active,
                'etudiants': etudiants, 'notes_existantes': notes_existantes,
                'periode_selectionnee': periode_selectionnee,
            })
        if Evaluation.objects.filter(
            ecole=ecole, programme__classe=classe, programme__matiere=matiere,
            periode_evaluation=periode,
        ).exists():
            messages.error(request, 'Des évaluations détaillées existent pour cette matière et cette période. Utilisez leur saisie.')
            return render(request, 'dashboard/notes/saisir_notes.html', {
                'classe': classe, 'matiere': matiere, 'annee_active': annee_active,
                'etudiants': etudiants, 'notes_existantes': notes_existantes,
                'periode_selectionnee': periode,
            }, status=409)
        notes_sauvegardees, erreurs = 0, 0

        for etudiant in etudiants:
            note_str = request.POST.get(f'note_{etudiant.pk}', '').strip()
            if note_str:
                try:
                    note_valeur = Decimal(note_str.replace(',', '.'))
                    if note_valeur < 0 or note_valeur > 20:
                        raise ValueError('La note doit être comprise entre 0 et 20.')
                    Note.objects.update_or_create(
                        etudiant=etudiant,
                        matiere=matiere,
                        periode_evaluation=periode,
                        annee_scolaire=annee_active,
                        ecole=ecole,
                        defaults={
                            'valeur': note_valeur,
                            'type_evaluation': type_eval,
                            'date_evaluation': parsed_date,
                        }
                    )
                    notes_sauvegardees += 1
                except (ValueError, InvalidOperation):
                    erreurs += 1
                    messages.warning(request, f"La note de {etudiant.prenom} {etudiant.nom} est invalide.")
                except Exception as e:
                    erreurs += 1
                    messages.error(request, f"Erreur pour {etudiant.prenom} {etudiant.nom} : {e}")

        if notes_sauvegardees:
            messages.success(request, f"{notes_sauvegardees} notes enregistrées ou mises à jour avec succès.")
        if erreurs == 0:
            return redirect('notes_par_classe_matiere', classe_id=classe_id, matiere_id=matiere_id)

    return render(request, 'dashboard/notes/saisir_notes.html', {
        'classe': classe,
        'matiere': matiere,
        'annee_active': annee_active,
        'etudiants': etudiants,
        'notes_existantes': notes_existantes,
        'periode_selectionnee': periode_selectionnee,
    })


# ======================================================
# Modification individuelle d'une note
# ======================================================


@school_role_required('school_admin', 'director', 'teacher')
def liste_notes_par_classe(request, classe_id=None, matiere_id=None):
    """
    Liste des notes par classe et matière pour l'école de l'utilisateur.
    Si classe_id et matiere_id sont passés en GET ou URL, affiche les notes correspondantes.
    """
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Récupération de l'année scolaire active
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.error(request, "Veuillez définir une année scolaire active pour votre école.")
        return render(request, 'dashboard/notes/liste_notes_par_classe.html', {})

    # Priorité : URL parameters > GET parameters
    classe_id = classe_id or request.GET.get('classe_id')
    matiere_id = matiere_id or request.GET.get('matiere_id')

    toutes_les_classes = Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).order_by('nom_classe')
    toutes_les_matieres = Matiere.objects.filter(ecole=ecole).order_by('nom')
    if is_teacher_account(request.user):
        assignments = assigned_programs(request.user, ecole, annee_active)
        toutes_les_classes = toutes_les_classes.filter(pk__in=assignments.values('classe_id'))
        toutes_les_matieres = toutes_les_matieres.filter(pk__in=assignments.values('matiere_id'))

    classe = None
    matiere = None
    etudiants_avec_notes = {}

    if classe_id and matiere_id:
        classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole, annee_scolaire=annee_active)
        matiere = get_object_or_404(Matiere, pk=matiere_id, ecole=ecole)
        if is_teacher_account(request.user) and not teacher_can_teach(request.user, ecole, classe.pk, matiere.pk, annee_active):
            return HttpResponse('Vous n’êtes pas affecté à cette matière.', status=403)

        # Étudiants de la classe pour l'année scolaire active
        etudiants = Etudiant.objects.filter(
            ecole=ecole,
            inscriptions__annee_scolaire=annee_active, inscriptions__classe=classe, inscriptions__statut='active'
        ).order_by('nom', 'prenom')

        # Récupérer toutes les notes en une seule requête
        notes = Note.objects.filter(
            etudiant__in=etudiants,
            matiere=matiere,
            annee_scolaire=annee_active,
            ecole=ecole
        ).select_related('etudiant').order_by('etudiant__nom', 'date_evaluation')

        # Construire un dictionnaire {étudiant: [notes]}
        etudiants_avec_notes = {etudiant: [] for etudiant in etudiants}
        for note in notes:
            etudiants_avec_notes[note.etudiant].append(note)

    context = {
        'classe': classe,
        'matiere': matiere,
        'annee_active': annee_active,
        'toutes_les_classes': toutes_les_classes,
        'toutes_les_matieres': toutes_les_matieres,
        'etudiants_avec_notes': etudiants_avec_notes,
    }

    return render(request, 'dashboard/notes/liste_notes_par_classe.html', context)

# ======================================================
# EXPORT DES NOTES VERS EXCEL
# ======================================================


@school_role_required('school_admin', 'director')
def export_notes_excel(request):
    """
    Exporte les notes filtrées par classe, matière et période au format Excel.
    Paramètres GET : classe_id, matiere_id, periode
    """
    ecole = get_user_ecole(request)
    if not ecole:
        return HttpResponse('Aucune école associée à ce compte.', status=403)
    classe_id = request.GET.get('classe_id')
    matiere_id = request.GET.get('matiere_id')
    periode = request.GET.get('periode', 'Toutes')

    annee_scolaire = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_scolaire:
        messages.error(request, "Aucune année scolaire active trouvée.")
        return redirect('liste_notes_par_classe_matiere')

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="notes_{periode}_{annee_scolaire.annee}.xlsx"'

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = f"Notes {periode}"

    headers = ["MATRICULE", "NOM", "PRENOM", "CLASSE", "MATIERE", "NOTE", "PERIODE", "ANNEE_SCOLAIRE"]
    sheet.append(headers)

    notes = Note.objects.filter(ecole=ecole, annee_scolaire=annee_scolaire)
    if classe_id:
        classe = get_object_or_404(Classe, pk=classe_id, ecole=ecole, annee_scolaire=annee_scolaire)
        notes = notes.filter(
            etudiant__inscriptions__classe=classe,
            etudiant__inscriptions__annee_scolaire=annee_scolaire,
        )
    if matiere_id:
        matiere = get_object_or_404(Matiere, pk=matiere_id, ecole=ecole)
        notes = notes.filter(matiere=matiere)
    if periode != 'Toutes':
        notes = notes.filter(periode_evaluation=periode)

    notes = notes.select_related('etudiant', 'matiere').order_by('etudiant__nom', 'etudiant__prenom')
    classes_annuelles = {
        inscription.etudiant_id: inscription.classe.nom_classe if inscription.classe_id else 'N/A'
        for inscription in Inscription.objects.filter(ecole=ecole, annee_scolaire=annee_scolaire)
        .select_related('classe')
    }

    for note in notes:
        sheet.append([
            note.etudiant.numero_matricule,
            note.etudiant.nom,
            note.etudiant.prenom,
            classes_annuelles.get(note.etudiant_id, 'N/A'),
            note.matiere.nom,
            note.valeur,
            note.periode_evaluation,
            note.annee_scolaire.annee
        ])

    workbook.save(response)
    return response


# ======================================================
# IMPORT DES NOTES DEPUIS EXCEL
# ======================================================


@school_role_required('school_admin', 'director')
def import_notes_excel(request):
    """Importe un fichier .xlsx pour l'école et l'année active du compte."""
    ecole = get_user_ecole(request)
    if not ecole:
        return HttpResponse('Aucune école associée à ce compte.', status=403)
    if request.method != 'POST' or 'file' not in request.FILES:
        return render(request, 'dashboard/notes/import_notes.html', {'page_title': "Importer des Notes"})

    excel_file = request.FILES['file']
    if not excel_file.name.lower().endswith('.xlsx'):
        messages.error(request, "Le fichier doit être au format .xlsx.")
        return redirect('import_notes_excel')
    if excel_file.size > 10 * 1024 * 1024:
        messages.error(request, "Le fichier dépasse la taille maximale de 10 Mo.")
        return redirect('import_notes_excel')

    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.error(request, "Aucune année scolaire active n'est définie pour votre école.")
        return redirect('liste_notes_par_classe_matiere')

    try:
        workbook = openpyxl.load_workbook(excel_file, read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        prepared, errors = [], []
        for row_number, row in enumerate(rows, start=2):
            if not row or not row[0]:
                continue
            try:
                matricule, nom, prenom, classe_nom, matiere_nom, raw_value, periode = row[:7]
                if periode == 'Annuelle':
                    raise ValueError(MESSAGE_NOTE_ANNUELLE)
                etudiant = Etudiant.objects.get(numero_matricule=str(matricule).strip(), ecole=ecole)
                matiere = Matiere.objects.get(nom=str(matiere_nom).strip(), ecole=ecole)
                value = Decimal(str(raw_value).replace(',', '.'))
                if value < 0 or value > 20:
                    raise ValueError('la note doit être comprise entre 0 et 20')
                if periode not in PERIODES_NOTES_SAISISSABLES:
                    raise ValueError('période d’évaluation inconnue')
                inscription = Inscription.objects.select_related('classe').filter(
                    ecole=ecole, etudiant=etudiant, annee_scolaire=annee_active, statut='active',
                ).first()
                if not inscription or not inscription.classe_id:
                    raise ValueError("l'élève n'a pas d'inscription active dans une classe")
                if classe_nom and str(classe_nom).strip() != inscription.classe.nom_classe:
                    raise ValueError('la classe du fichier ne correspond pas à celle de l’élève')
                if not ProgrammeMatiere.objects.filter(
                    ecole=ecole, classe=inscription.classe, matiere=matiere,
                ).exists():
                    raise ValueError("la matière n'est pas au programme de la classe")
                if Evaluation.objects.filter(
                    ecole=ecole, programme__classe=inscription.classe,
                    programme__matiere=matiere, periode_evaluation=periode,
                ).exists():
                    raise ValueError('des évaluations détaillées existent pour cette matière et cette période')
                prepared.append((etudiant, matiere, value, periode))
            except Etudiant.DoesNotExist:
                errors.append(f"Ligne {row_number} : matricule introuvable dans cette école.")
            except Matiere.DoesNotExist:
                errors.append(f"Ligne {row_number} : matière introuvable dans cette école.")
            except (ValueError, TypeError, InvalidOperation) as exc:
                errors.append(f"Ligne {row_number} : {exc}.")
            except Exception as exc:
                errors.append(f"Ligne {row_number} : données invalides ({exc}).")
        workbook.close()

        if errors:
            messages.error(request, f"Import annulé : {len(errors)} ligne(s) à corriger. Première erreur : {errors[0]}")
            return redirect('import_notes_excel')

        with transaction.atomic():
            for etudiant, matiere, value, periode in prepared:
                Note.objects.update_or_create(
                    etudiant=etudiant, matiere=matiere, periode_evaluation=periode,
                    annee_scolaire=annee_active, ecole=ecole,
                    defaults={'valeur': value},
                )
        messages.success(request, f"Import réussi : {len(prepared)} ligne(s) traitée(s).")
    except Exception as exc:
        messages.error(request, f"Erreur lors de l'import : {exc}")
    return redirect('liste_notes_par_classe_matiere')
