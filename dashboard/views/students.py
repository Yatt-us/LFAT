"""Vues students du tableau de bord."""

from .common import *
from ..models import DocumentEmis, ModeleDocument
from ..access import school_role_required
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from parcours_scolaire.models import AffectationClasse
from parcours_scolaire.services import synchroniser_affectation


def _inscription_pour_annee(ecole, etudiant, annee_scolaire):
    """Lire l'affectation annuelle sans déduire une classe des champs historiques."""
    if annee_scolaire is None:
        return None
    return (
        Inscription.objects.filter(
            ecole=ecole, etudiant=etudiant, annee_scolaire=annee_scolaire,
        )
        .select_related('classe', 'annee_scolaire')
        .first()
    )


@school_role_required('school_admin', 'director', 'secretary')
def liste_etudiants(request):
    ecole = get_user_ecole(request)
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    etudiants = Etudiant.objects.filter(ecole=ecole)
    if annee_active:
        inscriptions_actives = Inscription.objects.filter(
            ecole=ecole, annee_scolaire=annee_active, statut='active'
        ).select_related('classe', 'annee_scolaire')
        etudiants = etudiants.filter(
            inscriptions__ecole=ecole,
            inscriptions__annee_scolaire=annee_active,
            inscriptions__statut='active',
        ).prefetch_related(Prefetch('inscriptions', queryset=inscriptions_actives, to_attr='inscriptions_actives'))
    etudiants = etudiants.distinct()
    toutes_les_classes = list(
        Classe.objects.filter(ecole=ecole, annee_scolaire=annee_active).order_by('nom_classe')
    ) if annee_active else []

    selected_classe_id = None
    requested_classe_id = request.GET.get('classe')
    if requested_classe_id:
        try:
            requested_classe_id = int(requested_classe_id)
            if requested_classe_id not in {classe.pk for classe in toutes_les_classes}:
                raise ValueError
            selected_classe_id = requested_classe_id
            etudiants = etudiants.filter(
                inscriptions__ecole=ecole,
                inscriptions__annee_scolaire=annee_active,
                inscriptions__statut='active',
                inscriptions__classe_id=selected_classe_id,
            )
        except (ValueError, TypeError):
            messages.warning(request, "Le filtre de classe sélectionné n'est pas valide.")

    etudiants = etudiants.order_by('nom', 'prenom')

    can_archive = request.user.is_superuser or request.user.profile.role in ('school_admin', 'director')
    students = []
    for etudiant in etudiants:
        inscription = etudiant.inscriptions_actives[0] if annee_active and etudiant.inscriptions_actives else None
        classe = inscription.classe if inscription else None
        students.append({
            'id': etudiant.pk,
            'nom': etudiant.nom,
            'prenom': etudiant.prenom,
            'matricule': etudiant.numero_matricule or '',
            'classeId': classe.pk if classe else None,
            'classeNom': classe.nom_classe if classe else '',
            'anneeInscription': inscription.annee_scolaire.annee if inscription else '',
            'statut': 'Actif' if inscription else etudiant.statut,
            'photoUrl': reverse('student_photo', args=[etudiant.pk]) if etudiant.photo_profil else '',
            'detailUrl': reverse('detail_etudiant', args=[etudiant.pk]),
            'editUrl': reverse('modifier_etudiant', args=[etudiant.pk]),
            'archiveUrl': reverse('supprimer_etudiant', args=[etudiant.pk]) if can_archive else None,
        })

    students_payload = {
        'students': students,
        'classes': [{'id': classe.pk, 'nom': classe.nom_classe} for classe in toutes_les_classes],
        'year': annee_active.annee if annee_active else None,
        'selectedClassId': selected_classe_id,
        'createUrl': reverse('creer_etudiant'),
    }

    return render(request, 'dashboard/etudiants/liste_etudiants.html', {
        'students_payload': students_payload,
    })


# ------------------------------------------------------------------
# CRÉER ÉTUDIANT
# ------------------------------------------------------------------


@school_role_required('school_admin', 'director', 'secretary')
def creer_etudiant(request):
    # Récupérer l'école de l'utilisateur
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Formset pour les images du dossier d'inscription
    DossierFormSet = modelformset_factory(
        DossierInscriptionImage,
        form=DossierInscriptionImageForm,
        extra=3,
        can_delete=True
    )

    # Récupérer l'année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()
    if not annee_active:
        messages.error(request, "Créez et activez une année scolaire avant d'inscrire un élève.")
        return redirect('liste_annees_scolaires')

    if request.method == 'POST':
        form = EtudiantForm(
            request.POST,
            request.FILES,
            ecole=ecole,  # ⚡ Passer l'école pour filtrer classes et années
        )
        form.fields['annee_scolaire_inscription'].initial = annee_active
        form.fields['annee_scolaire_inscription'].disabled = True
        form.instance.ecole = ecole
        formset = DossierFormSet(
            request.POST,
            request.FILES,
            queryset=DossierInscriptionImage.objects.none()
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # Créer l'étudiant
                etudiant = form.save(commit=False)
                etudiant.ecole = ecole
                # Assigner l'année active si non fournie
                etudiant.annee_scolaire_inscription = annee_active
                classe_inscription = etudiant.classe
                statut_inscription = {
                    'Actif': 'active', 'Suspendu': 'suspendue',
                    'Ancien': 'terminee', 'Radié': 'transferee',
                }[etudiant.statut]
                if statut_inscription != 'active':
                    etudiant.classe = None
                etudiant.save()
                inscription = Inscription(
                    ecole=ecole, etudiant=etudiant, annee_scolaire=annee_active,
                    classe=classe_inscription, statut=statut_inscription,
                )
                inscription.full_clean()
                inscription.save()
                synchroniser_affectation(inscription, date_effet=timezone.localdate(), acteur=request.user)

                # Sauvegarde des images du dossier
                for f in formset:
                    if f.cleaned_data and not f.cleaned_data.get('DELETE'):
                        dossier_image = f.save(commit=False)
                        dossier_image.etudiant = etudiant
                        dossier_image.ecole = ecole
                        dossier_image.save()

                messages.success(
                    request,
                    f"L'élève {etudiant.prenom} {etudiant.nom} a été ajouté avec succès."
                )
                return redirect('detail_etudiant', etudiant_id=etudiant.pk)
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = EtudiantForm(
            ecole=ecole,
            initial={'annee_scolaire_inscription': annee_active}
        )
        form.fields['annee_scolaire_inscription'].disabled = True
        formset = DossierFormSet(queryset=DossierInscriptionImage.objects.none())

    return render(
        request,
        'dashboard/etudiants/creer_etudiant.html',
        {'form': form, 'formset': formset, 'annee_active': annee_active}
    )


# ------------------------------------------------------------------
# DÉTAIL ÉTUDIANT
# ------------------------------------------------------------------


@school_role_required('school_admin', 'director', 'secretary', 'accountant')
def detail_etudiant(request, etudiant_id):
    # Récupérer l'école de l'utilisateur connecté
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # Étudiant filtré par école
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)

    # Année scolaire active pour cette école
    annee_active = AnneeScolaire.objects.filter(active=True, ecole=ecole).first()

    role = getattr(getattr(request.user, 'profile', None), 'role', None)
    can_view_finances = request.user.is_superuser or role in ('school_admin', 'director', 'accountant')
    can_view_academics = role != 'accountant'
    can_manage_enrollment = request.user.is_superuser or role in ('school_admin', 'director', 'secretary')
    can_archive = request.user.is_superuser or role in ('school_admin', 'director')
    dossier_images = etudiant.dossier_images.filter(ecole=ecole) if can_view_academics else DossierInscriptionImage.objects.none()
    inscription_courante = _inscription_pour_annee(ecole, etudiant, annee_active)
    affectations_classe = AffectationClasse.objects.filter(
        inscription__ecole=ecole, inscription__etudiant=etudiant,
    ).select_related('classe', 'inscription__annee_scolaire', 'cree_par', 'termine_par').order_by(
        '-inscription__annee_scolaire__annee', '-date_debut', '-pk',
    ) if can_view_academics else AffectationClasse.objects.none()
    inscription_active = (
        inscription_courante if inscription_courante and inscription_courante.statut == 'active' else None
    )
    if can_view_academics:
        modeles_documents_libres = ModeleDocument.objects.filter(
            ecole=ecole, type_document=ModeleDocument.TYPE_AUTRE, actif=True,
        ).order_by('titre')
        documents_emis = DocumentEmis.objects.filter(
            ecole=ecole, etudiant=etudiant,
        ).select_related('annee_scolaire', 'modele').order_by('-date_emission')
    else:
        modeles_documents_libres = ModeleDocument.objects.none()
        documents_emis = DocumentEmis.objects.none()

    # Notes filtrées par école et année active (ou tout l'historique si besoin)
    notes = etudiant.notes.filter(
        ecole=ecole,
        annee_scolaire=annee_active
    ).select_related('matiere', 'annee_scolaire').order_by('-annee_scolaire', 'periode_evaluation')

    # Paiements filtrés par école
    paiements = etudiant.paiements.filter(
        ecole=ecole,
        annee_scolaire=annee_active
    ).select_related('annee_scolaire').order_by('-date_paiement')

    # Présences filtrées par école et année active
    presences = etudiant.presences.filter(
        ecole=ecole,
        annee_scolaire=annee_active
    ).select_related('matiere', 'annee_scolaire').order_by('-date')

    # Une créance représente le montant dû; chaque encaissement est compté une seule fois.
    from ..finance import creances_avec_total
    from decimal import Decimal
    if can_view_finances and annee_active:
        paiements = paiements.filter(annule=False, montant__gt=0)
        creances = list(creances_avec_total(ecole, annee_active, etudiant))
        paiements_annules = etudiant.paiements.filter(ecole=ecole, annee_scolaire=annee_active, annule=True)
        total_paye = paiements.aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
        total_du = sum((f.montant_du for f in creances), Decimal('0.00'))
        solde_restant = sum((f.solde_restant for f in creances), Decimal('0.00'))
    else:
        paiements = Paiement.objects.none()
        creances = []
        paiements_annules = Paiement.objects.none()
        total_paye = total_du = solde_restant = Decimal('0.00')

    # Statistiques de présence
    stats_presences = presences.values('statut').annotate(total=Count('id'))
    total_jours_presents = next((x['total'] for x in stats_presences if x['statut'] == 'Présent'), 0)
    total_jours_absents_statut_absent = next((x['total'] for x in stats_presences if x['statut'] == 'Absent'), 0)
    total_jours_retard = next((x['total'] for x in stats_presences if x['statut'] == 'Retard'), 0)
    total_jours_excuses = next((x['total'] for x in stats_presences if x['statut'] == 'Excusé'), 0)
    total_jours_absents = total_jours_absents_statut_absent + total_jours_excuses

    context = {
        'etudiant': etudiant,
        'dossier_images': dossier_images,
        'modeles_documents_libres': modeles_documents_libres,
        'documents_emis': documents_emis,
        'notes': notes,
        'paiements': paiements,
        'paiements_annules': paiements_annules,
        'creances': creances,
        'inscription_courante': inscription_courante,
        'inscription_active': inscription_active,
        'affectations_classe': affectations_classe,
        'can_view_finances': can_view_finances,
        'can_view_academics': can_view_academics,
        'can_manage_enrollment': can_manage_enrollment,
        'can_archive': can_archive,
        'presences': presences,
        'total_paye': total_paye,
        'total_du': total_du,
        'solde_restant': solde_restant,
        'total_jours_presents': total_jours_presents,
        'total_jours_absents': total_jours_absents,
        'total_jours_absents_statut_absent': total_jours_absents_statut_absent,
        'total_jours_retard': total_jours_retard,
        'total_jours_excuses': total_jours_excuses,
        'annee_active': annee_active,
    }

    return render(request, 'dashboard/etudiants/detail_etudiant.html', context)




# ------------------------------------------------------------------
# MODIFIER ÉTUDIANT
# ------------------------------------------------------------------


@school_role_required('school_admin', 'director', 'secretary')
def modifier_etudiant(request, etudiant_id):
    """
    Modifier un étudiant et ses dossiers d'inscription.
    Filtrage strict par l'école de l'utilisateur.
    """
    # 🔹 Récupération de l'école
    ecole = get_user_ecole(request)
    if not ecole:
        messages.error(request, "Vous n'êtes associé à aucune école.")
        return redirect('dashboard_accueil')

    # 🔹 Récupération de l'étudiant lié à cette école
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    inscription_courante = _inscription_pour_annee(ecole, etudiant, annee_active)

    # 🔹 Formset pour gérer les images/dossiers
    DossierFormSet = modelformset_factory(
        DossierInscriptionImage,
        form=DossierInscriptionImageForm,
        extra=1,
        can_delete=True
    )

    if request.method == 'POST':
        # ⚡ Important : passer l'école au formulaire pour filtrer les classes et années
        form = EtudiantForm(request.POST, request.FILES, instance=etudiant, ecole=ecole)
        form.fields.pop('classe')
        form.fields.pop('annee_scolaire_inscription')
        if inscription_courante:
            form.fields.pop('statut')
        formset = DossierFormSet(
            request.POST,
            request.FILES,
            queryset=DossierInscriptionImage.objects.filter(etudiant=etudiant, ecole=ecole)
        )

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                etudiant = form.save()
                
                for f in formset:
                    if f.cleaned_data:
                        if f.cleaned_data.get('DELETE') and f.instance.pk:
                            f.instance.delete()
                        else:
                            dossier_image = f.save(commit=False)
                            dossier_image.etudiant = etudiant
                            dossier_image.ecole = ecole
                            dossier_image.save()
                
                messages.success(request, f"Les informations de {etudiant.prenom} {etudiant.nom} ont été mises à jour.")
                return redirect('detail_etudiant', etudiant_id=etudiant.pk)
        else:
            messages.error(request, "Veuillez corriger les erreurs dans le formulaire.")
    else:
        form = EtudiantForm(instance=etudiant, ecole=ecole)
        form.fields.pop('classe')
        form.fields.pop('annee_scolaire_inscription')
        if inscription_courante:
            form.fields.pop('statut')
        formset = DossierFormSet(queryset=DossierInscriptionImage.objects.filter(etudiant=etudiant))

    return render(request, 'dashboard/etudiants/modifier_etudiant.html', {
        'form': form,
        'formset': formset,
        'etudiant': etudiant,
        'annee_active': annee_active,
        'inscription_courante': inscription_courante,
    })


@school_role_required('school_admin', 'director')
def supprimer_etudiant(request, etudiant_id):
    """
    Supprimer un étudiant (filtré par école de l'utilisateur).
    """
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)

    if request.method == 'POST':
        nom_complet = f"{etudiant.prenom} {etudiant.nom}"
        try:
            with transaction.atomic():
                inscriptions_actives = list(etudiant.inscriptions.select_for_update().filter(
                    ecole=ecole, statut='active',
                ))
                for inscription in inscriptions_actives:
                    inscription.statut = 'terminee'
                    inscription.save(update_fields=['statut'])
                    synchroniser_affectation(inscription, date_effet=timezone.localdate(), acteur=request.user)
                etudiant.statut = 'Ancien'
                etudiant.classe = None
                etudiant.save(update_fields=['statut', 'classe'])
        except ValidationError as erreur:
            messages.error(request, 'Archivage impossible : ' + ' '.join(erreur.messages))
            return redirect('detail_etudiant', etudiant_id=etudiant.pk)
        messages.success(request, f"Le dossier de {nom_complet} a été archivé. Son historique est conservé.")
        return redirect('liste_etudiants')

    return render(request, 'dashboard/etudiants/confirmer_suppression_etudiant.html', {
        'etudiant': etudiant
    })



# --- Vues pour les notes, paiements, présences (création/modification liée à un élève) ---
# Vous pouvez les créer comme des vues séparées ou des modales dans la page de détail de l'élève


@school_role_required('school_admin', 'director', 'secretary')
def inscrire_etudiant(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee_active = AnneeScolaire.objects.filter(ecole=ecole, active=True).first()
    if not annee_active:
        messages.error(request, "Aucune année scolaire active n'est définie.")
        return redirect('liste_annees_scolaires')

    inscription = _inscription_pour_annee(ecole, etudiant, annee_active)
    if request.method == 'POST':
        form = InscriptionForm(request.POST, instance=inscription, ecole=ecole, annee_scolaire=annee_active)
        if form.is_valid():
            inscription = form.save(commit=False)
            inscription.ecole = ecole
            inscription.etudiant = etudiant
            inscription.annee_scolaire = annee_active
            try:
                with transaction.atomic():
                    inscription.full_clean()
                    inscription.save()
                    synchroniser_affectation(inscription, date_effet=timezone.localdate(), acteur=request.user)
                    # Ces champs anciens restent synchronisés pour les autres écrans.
                    status_map = {'active': 'Actif', 'suspendue': 'Suspendu', 'terminee': 'Ancien', 'transferee': 'Radié'}
                    etudiant.statut = status_map[inscription.statut]
                    etudiant.classe = inscription.classe if inscription.statut == 'active' else None
                    etudiant.save(update_fields=['statut', 'classe'])
                messages.success(request, f"{etudiant.prenom} {etudiant.nom} est inscrit pour {annee_active.annee}.")
                return redirect('detail_etudiant', etudiant_id=etudiant.pk)
            except ValidationError as erreur:
                form.add_error(None, ' '.join(erreur.messages))
            except IntegrityError:
                form.add_error(None, 'Le changement de classe a été modifié en parallèle. Rechargez la page.')
    else:
        form = InscriptionForm(instance=inscription, ecole=ecole, annee_scolaire=annee_active)
    return render(request, 'dashboard/etudiants/inscrire_etudiant.html', {
        'form': form, 'etudiant': etudiant, 'annee_active': annee_active,
        'inscription_courante': inscription,
    })
