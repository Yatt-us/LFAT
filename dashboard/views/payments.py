"""Vues des créances scolaires et des encaissements."""

import base64
import mimetypes
from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
from django.utils import timezone

from .common import *
from ..access import school_role_required
from ..finance import creances_avec_total
from ..forms import CreanceScolaireForm


def _annee_active(ecole):
    return AnneeScolaire.objects.filter(ecole=ecole, active=True).first()


def _inscrit(ecole, etudiant, annee):
    return Inscription.objects.filter(
        ecole=ecole, etudiant=etudiant, annee_scolaire=anne, statut='active',
    ).exists()


@school_role_required('school_admin', 'director', 'accountant')
def liste_paiements_par_classe_etudiant(request):
    ecole = get_user_ecole(request)
    annee = _annee_active(ecole)
    if annee is None:
        return render(request, 'dashboard/paiements/paiements_par_classe_etudiant.html', {
            'annee_active': None, 'data_par_classe': [], 'toutes_les_classes': [],
        })

    classes = Classe.objects.filter(ecole=ecole, annee_scolaire=annee).order_by('nom_classe')
    classe_id = request.GET.get('classe_filter_id')
    try:
        classe_id = int(classe_id) if classe_id else None
    except (ValueError, TypeError):
        classe_id = None
    if classe_id:
        classes = classes.filter(pk=classe_id)
    selected_statut = request.GET.get('statut_filter')
    if selected_statut not in ('payes', 'impayes_partiels'):
        selected_statut = None

    inscriptions = Inscription.objects.filter(
        ecole=ecole, annee_scolaire=annee, statut='active',
        classe__in=classes, etudiant__ecole=ecole,
    ).select_related('etudiant', 'classe').order_by('classe__nom_classe', 'etudiant__nom', 'etudiant__prenom')

    frais_par_eleve = {}
    for frais in creances_avec_total(ecole, annee).select_related('etudiant'):
        frais_par_eleve.setdefault(frais.etudiant_id, []).append(frais)

    classes_data = {}
    for inscription in inscriptions:
        frais = frais_par_eleve.get(inscription.etudiant_id, [])
        if selected_statut == 'payes':
            frais = [f for f in frais if f.statut == 'Payé']
        elif selected_statut == 'impayes_partiels':
            frais = [f for f in frais if f.statut != 'Payé']
        if not frais:
            continue
        classes_data.setdefault(inscription.classe_id, {
            'classe': inscription.classe, 'etudiants_data': [],
        })['etudiants_data'].append({
            'etudiant': inscription.etudiant,
            'creances': frais,
            'total_du': sum((f.montant_du for f in frais), Decimal('0.00')),
            'total_paye': sum((f.montant_paye for f in frais), Decimal('0.00')),
            'total_restant': sum((f.solde_restant for f in frais), Decimal('0.00')),
        })
    return render(request, 'dashboard/paiements/paiements_par_classe_etudiant.html', {
        'annee_active': annee,
        'data_par_classe': list(classes_data.values()),
        'toutes_les_classes': Classe.objects.filter(ecole=ecole, annee_scolaire=annee).order_by('nom_classe'),
        'selected_classe_id': classe_id,
        'selected_statut': selected_statut,
    })


@school_role_required('school_admin', 'director', 'accountant')
def liste_paiements_impayes(request):
    ecole = get_user_ecole(request)
    annee = _annee_active(ecole)
    if annee is None:
        return render(request, 'dashboard/paiements/paiements_impayes.html', {
            'creances_impayees': [], 'annee_active': None,
        })
    creances = [
        f for f in creances_avec_total(ecole, annee)
        .filter(etudiant__inscriptions__annee_scolaire=annee, etudiant__inscriptions__statut='active')
        .select_related('etudiant', 'etudiant__classe')
        if f.solde_restant > 0 or f.a_verifier
    ]
    return render(request, 'dashboard/paiements/paiements_impayes.html', {
        'creances_impayees': creances, 'annee_active': annee,
    })


@school_role_required('school_admin', 'director', 'accountant')
def liste_paiements_payes(request):
    ecole = get_user_ecole(request)
    annee = _annee_active(ecole)
    paiements = Paiement.objects.none()
    if annee:
        paiements = Paiement.objects.filter(
            ecole=ecole, etudiant__ecole=ecole, annee_scolaire=annee,
            annule=False, montant__gt=0,
        ).select_related('etudiant', 'creance').order_by('-date_paiement', '-pk')
    return render(request, 'dashboard/paiements/paiements_payes.html', {
        'paiements_payes': paiements, 'annee_active': annee,
    })


@school_role_required('school_admin', 'director', 'accountant')
def generer_recu_paiement(request, paiement_id):
    """
    Génère un reçu PDF pour un paiement spécifique.
    Utilise wkhtmltopdf si disponible, sinon WeasyPrint comme solution de secours.
    Inclut automatiquement le logo de l’école dans le PDF.
    """

    # Le reçu reste dans le périmètre de l'école du compte connecté.
    ecole = get_user_ecole(request)
    if not ecole:
        return HttpResponse('Aucune école associée à ce compte.', status=403)
    paiement = get_object_or_404(
        Paiement.objects.select_related('etudiant', 'ecole', 'creance', 'annee_scolaire'),
        pk=paiement_id, ecole=ecole, etudiant__ecole=ecole,
        annee_scolaire__ecole=ecole, annule=False,
    )

    etudiant = paiement.etudiant
    ecole = paiement.ecole
    inscription_paiement = (
        Inscription.objects.filter(
            ecole=ecole, etudiant=etudiant, annee_scolaire=paiement.annee_scolaire,
        )
        .select_related('classe')
        .first()
    )

    # Le convertisseur PDF n’a pas la session du lecteur : le logo est incorporé.
    logo_url = ""
    if ecole.logo:
        try:
            mime = mimetypes.guess_type(ecole.logo.name)[0] or "image/png"
            with ecole.logo.open("rb") as logo_file:
                contenu = base64.b64encode(logo_file.read()).decode("ascii")
            logo_url = f"data:{mime};base64,{contenu}"
        except (OSError, ValueError):
            logo_url = ""

    # --- 3️⃣ Contexte du reçu ---
    context = {
        'paiement': paiement,
        'etudiant': etudiant,
        'ecole': ecole,
        'inscription_paiement': inscription_paiement,
        'logo_url': logo_url,  # ajouté pour affichage dans le template
        
    }

    # --- 4️⃣ Rendu HTML ---
    html_string = render_to_string('dashboard/paiements/recu_paiement.html', context)

    # --- 5️⃣ Options wkhtmltopdf ---
    options = {
        'page-size': 'A5',
        'encoding': "UTF-8",
        'no-outline': None,
        'margin-top': '0.4in',
        'margin-bottom': '0.4in',
        'margin-left': '0.3in',
        'margin-right': '0.3in',
    }

    pdf_data = None

    # --- 6️⃣ Génération du PDF ---
    try:
        # Cherche wkhtmltopdf sur le système
        path_wkhtmltopdf = '/usr/bin/wkhtmltopdf'
        if not os.path.exists(path_wkhtmltopdf):
            path_wkhtmltopdf = shutil.which("wkhtmltopdf")

        if path_wkhtmltopdf:
            config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
            pdf_data = pdfkit.from_string(html_string, False, options=options, configuration=config)
        else:
            raise OSError("wkhtmltopdf non trouvé")

    except Exception:
        # Rendu PDF disponible même si wkhtmltopdf n'est pas installé.
        pdf_data = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    # --- 8️⃣ Réponse HTTP ---
    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Recu_{etudiant.nom}_{paiement.id}.pdf"'
    return response






@school_role_required('school_admin', 'director', 'accountant')
def creer_creance_scolaire(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee = _annee_active(ecole)
    if annee is None:
        messages.error(request, "Définissez une année scolaire active avant d'ajouter un frais.")
        return redirect('liste_annees_scolaires')
    if not _inscrit(ecole, etudiant, annee):
        messages.error(request, "Inscrivez cet élève pour l'année active avant d'ajouter un frais.")
        return redirect('detail_etudiant', etudiant_id=etudiant_id)
    form = CreanceScolaireForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        creance = form.save(commit=False)
        creance.ecole = ecole
        creance.etudiant = etudiant
        creance.annee_scolaire = annee
        creance.full_clean()
        creance.save()
        messages.success(request, "Frais scolaire enregistré.")
        return redirect('detail_etudiant', etudiant_id=etudiant_id)
    return render(request, 'dashboard/paiements/form_creance.html', {
        'form': form, 'etudiant': etudiant, 'annee_active': annee, 'action': 'Ajouter',
    })


@school_role_required('school_admin', 'director', 'accountant')
def modifier_creance_scolaire(request, pk):
    ecole = get_user_ecole(request)
    creance = get_object_or_404(
        CreanceScolaire.objects.select_related('etudiant', 'annee_scolaire'),
        pk=pk, ecole=ecole, etudiant__ecole=ecole, annee_scolaire__ecole=ecole,
    )
    form = CreanceScolaireForm(request.POST or None, instance=creance)
    if request.method == 'POST' and form.is_valid():
        montant = form.cleaned_data['montant_du']
        confirme = form.cleaned_data.get('montant_confirme', False)
        encaisse = creance.paiements.filter(annule=False).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
        if confirme and montant < encaisse:
            form.add_error('montant_du', "Pour confirmer ce montant, il doit couvrir les encaissements.")
        else:
            updated = form.save(commit=False)
            if confirme:
                updated.a_verifier = False
            updated.full_clean()
            updated.save()
            messages.success(request, "Frais scolaire mis à jour.")
            return redirect('detail_etudiant', etudiant_id=creance.etudiant_id)
    return render(request, 'dashboard/paiements/form_creance.html', {
        'form': form, 'etudiant': creance.etudiant,
        'annee_active': creance.annee_scolaire, 'action': 'Modifier',
        'creance': creance,
    })


def _enregistrer_paiement(form, request, correction=False):
    if not form.is_valid():
        return False
    creance = form.cleaned_data['creance']
    with transaction.atomic():
        verrouillee = CreanceScolaire.objects.select_for_update().get(pk=creance.pk)
        encaisse = verrouillee.paiements.filter(annule=False).exclude(
            pk=form.instance.pk,
        ).aggregate(total=Sum('montant'))['total'] or Decimal('0.00')
        if verrouillee.a_verifier or encaisse + form.cleaned_data['montant'] > verrouillee.montant_du:
            form.add_error('montant', "Le solde de ce frais a changé; rechargez la page.")
            return False
        paiement = form.save(commit=False)
        paiement.creance = verrouillee
        if correction:
            ancien = Paiement.objects.select_for_update().get(pk=paiement.pk)
            if ancien.annule:
                form.add_error(None, "Ce paiement a déjà été annulé.")
                return False
            ancien.annule = True
            ancien.annule_le = timezone.now()
            ancien.annule_par = request.user
            ancien.save(update_fields=["annule", "annule_le", "annule_par"])
            ancien_recu = ancien.recu_numero
            paiement.pk = None
            paiement._state.adding = True
            paiement.annule = False
            paiement.annule_le = None
            paiement.annule_par = None
            paiement.montant_du = None
            paiement.statut = "Payé"
            if paiement.recu_numero == ancien_recu:
                paiement.recu_numero = None
        paiement.enregistre_par = request.user
        paiement.full_clean()
        paiement.save()
    return True


@school_role_required('school_admin', 'director', 'accountant')
def ajouter_paiement(request, etudiant_id):
    ecole = get_user_ecole(request)
    etudiant = get_object_or_404(Etudiant, pk=etudiant_id, ecole=ecole)
    annee = _annee_active(ecole)
    if annee is None:
        messages.error(request, "Définissez une année scolaire active avant d'enregistrer un paiement.")
        return redirect('liste_annees_scolaires')
    if not _inscrit(ecole, etudiant, annee):
        messages.error(request, "L'élève doit être inscrit pour l'année active.")
        return redirect('detail_etudiant', etudiant_id=etudiant_id)
    if not CreanceScolaire.objects.filter(ecole=ecole, etudiant=etudiant, annee_scolaire=annee).exists():
        messages.info(request, "Créez d'abord le frais à payer.")
        return redirect('creer_creance_scolaire', etudiant_id=etudiant_id)
    form = PaiementForm(
        request.POST or None, ecole=ecole, etudiant=etudiant, annee_scolaire=annee,
    )
    if request.method == 'POST' and _enregistrer_paiement(form, request):
        messages.success(request, "Paiement enregistré.")
        return redirect('detail_etudiant', etudiant_id=etudiant_id)
    return render(request, 'dashboard/etudiants/ajouter_paiement.html', {
        'form': form, 'etudiant': etudiant, 'annee_active': annee,
    })


@school_role_required('school_admin', 'director', 'accountant')
def modifier_paiement(request, pk):
    ecole = get_user_ecole(request)
    paiement = get_object_or_404(
        Paiement.objects.select_related('etudiant', 'creance', 'annee_scolaire'),
        pk=pk, ecole=ecole, etudiant__ecole=ecole, annule=False,
    )
    if paiement.creance_id is None:
        raise Http404("Ce paiement historique doit être rapproché d'un frais avant correction.")
    form = PaiementForm(
        request.POST or None, instance=paiement, ecole=ecole,
        etudiant=paiement.etudiant, annee_scolaire=paiement.annee_scolaire,
    )
    if request.method == 'POST' and _enregistrer_paiement(form, request, correction=True):
        messages.success(request, "Paiement corrigé. L'ancienne écriture a été annulée et conservée.")
        return redirect('detail_etudiant', etudiant_id=paiement.etudiant_id)
    return render(request, 'dashboard/etudiants/modifier_paiement.html', {
        'form': form, 'paiement': paiement, 'etudiant': paiement.etudiant,
    })


@school_role_required('school_admin', 'director', 'accountant')
def supprimer_paiement(request, pk):
    ecole = get_user_ecole(request)
    paiement = get_object_or_404(
        Paiement.objects.select_related('etudiant'), pk=pk, ecole=ecole,
        etudiant__ecole=ecole, annule=False,
    )
    if request.method == 'POST':
        paiement.annule = True
        paiement.annule_le = timezone.now()
        paiement.annule_par = request.user
        paiement.save(update_fields=['annule', 'annule_le', 'annule_par'])
        messages.success(request, "Paiement annulé. L'historique est conservé.")
        return redirect('detail_etudiant', etudiant_id=paiement.etudiant_id)
    return render(request, 'dashboard/etudiants/confirmer_suppression_paiement.html', {
        'paiement': paiement,
    })
