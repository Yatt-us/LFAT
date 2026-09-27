"""Navigation data shared by the Django fallback and the React shell.

Permissions still belong to Django views. This only hides actions that the
current account cannot use and sends no other school's data to the browser.
"""
from django.middleware.csrf import get_token
from django.urls import reverse

from .models import AnneeScolaire
from .tenant import school_for_user


ROLE_LABELS = {
    'school_admin': 'Administration',
    'director': 'Direction',
    'secretary': 'Secrétariat',
    'accountant': 'Comptabilité',
    'teacher': 'Enseignement',
}


def saas_shell(request):
    user = request.user
    if not user.is_authenticated:
        return {'shell_payload': {}}

    school = school_for_user(user)
    profile = getattr(user, 'profile', None)
    role = getattr(profile, 'role', None)
    if role is None and getattr(user, 'enseignant', None):
        role = 'teacher'
    manager = user.is_superuser or role in {'school_admin', 'director'}
    office = manager or role == 'secretary'
    teacher = manager or role == 'teacher'
    finance = manager or role == 'accountant'
    search = office or role == 'accountant'
    current = getattr(request.resolver_match, 'url_name', '') or ''

    def item(key, label, route, icon, *, names=(), contains=(), exclude=()):
        return {
            'id': key,
            'label': label,
            'href': reverse(route),
            'icon': icon,
            'active': (current in names or any(part in current for part in contains))
                  and not any(part in current for part in exclude),
        }

    sections = [
        {
            'label': 'Vue générale',
            'items': [item('dashboard', 'Tableau de bord', 'dashboard_accueil', 'grid', names=('dashboard_accueil',))],
        },
    ]
    academic = []
    if office:
        academic.append(item('students', 'Élèves', 'liste_etudiants', 'users', contains=('etudiant', 'recherche_etudiants'), exclude=('paiement', 'creance')))
    if office or teacher:
        academic.append(item('classes', 'Classes', 'liste_classes', 'layers', contains=('classe',), exclude=('presence', 'note', 'emploi_du_temps', 'paiement', 'creance')))
    if office:
        academic.append(item('teachers', 'Enseignants', 'liste_enseignants', 'briefcase', contains=('enseignant',)))
    if office or teacher:
        academic.append(item('subjects', 'Matières', 'liste_matieres', 'book', contains=('matiere',), exclude=('programme', 'note')))
    if teacher:
        academic.append(item('programs', 'Programmes', 'liste_programmes_matiere', 'list', contains=('programme',)))
        academic.append(item('grades', 'Notes', 'liste_notes_par_classe_matiere', 'edit', contains=('note', 'bulletin')))
        academic.append(item('evaluations', 'Évaluations', 'liste_evaluations', 'edit', contains=('evaluation',)))
        academic.append(item('attendance', 'Présences journalières', 'liste_presences', 'calendar', contains=('presence',)))
        academic.append(item('session-attendance', 'Appels par séance', 'vie_scolaire:liste_seances', 'calendar', contains=('seance', 'pointage', 'justification')))
        academic.append(item('schedule', 'Emploi du temps', 'liste_emplois_du_temps', 'clock', contains=('emploi_du_temps',)))
    if office:
        academic.append(item('years', 'Années scolaires', 'liste_annees_scolaires', 'calendar', contains=('annee_scolaire',)))
    if academic:
        sections.append({'label': 'Vie scolaire', 'items': academic})

    management = []
    if finance:
        management.append(item('payments', 'Paiements', 'liste_paiements_par_classe_etudiant', 'wallet', contains=('paiement', 'creance')))
    if manager:
        management.append(item('documents', 'Modèles de documents', 'modeles_documents', 'file', contains=('modele_document',)))
        management.append(item('bulletin-rules', 'Règles des bulletins', 'liste_regles_bulletin_annuel', 'file', contains=('regle_bulletin_annuel',)))
        management.append(item('settings', 'Paramètres', 'ecole_settings', 'settings', names=('ecole_settings',)))
    if management:
        sections.append({'label': 'Administration', 'items': management})

    active_item = next((entry for group in sections for entry in group['items'] if entry['active']), None)
    display_name = user.get_full_name().strip() or user.username
    words = display_name.split()
    initials = ''.join(word[0] for word in words[:2]).upper() if words else '?'
    year = AnneeScolaire.objects.filter(ecole=school, active=True).first() if school else None
    payload = {
        'school_name': school.nom_etablissement if school else 'Gestion scolaire',
        'school_logo_url': reverse('school_logo', args=[school.pk]) if school and school.logo else '',
        'year': year.annee if year else 'Année non définie',
        'user_name': display_name,
        'user_initials': initials,
        'role': ROLE_LABELS.get(role, 'Administration' if user.is_superuser else 'Compte scolaire'),
        'sections': sections,
        'page_title': active_item['label'] if active_item else 'Espace scolaire',
        'can_search': search,
        'search_url': reverse('recherche_etudiants_globale') if search else '',
        'password_url': reverse('password_change'),
        'logout_url': reverse('logout'),
        'csrf_token': get_token(request),
    }
    return {'shell_payload': payload}
