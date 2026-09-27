"""Role-based view access for school tenants."""
from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from .tenant import school_for_user


def school_role_required(*allowed_roles):
    allowed = set(allowed_roles)

    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            school = school_for_user(request.user)
            if school is None:
                return HttpResponseForbidden("Aucune école n'est associée à ce compte.")
            if request.user.is_superuser:
                return view(request, *args, **kwargs)
            profile = getattr(request.user, 'profile', None)
            role = profile.role if profile else ('teacher' if getattr(request.user, 'enseignant', None) else None)
            if role == 'teacher' and not getattr(request.user, 'enseignant', None):
                return HttpResponseForbidden("Aucune fiche enseignant n'est associée à ce compte.")
            if role not in allowed:
                return HttpResponseForbidden("Votre rôle ne permet pas cette action.")
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def assigned_programs(user, school, year=None):
    """Programme-matière affecté à l’enseignant connecté dans une école."""
    from .models import ProgrammeMatiere
    teacher = getattr(user, 'enseignant', None)
    if teacher is None or teacher.ecole_id != school.id:
        return ProgrammeMatiere.objects.none()
    queryset = ProgrammeMatiere.objects.filter(ecole=school, enseignant=teacher)
    if year is not None:
        queryset = queryset.filter(classe__annee_scolaire=year)
    return queryset


def teacher_can_teach(user, school, class_id, subject_id=None, year=None):
    queryset = assigned_programs(user, school, year).filter(classe_id=class_id)
    if subject_id is not None:
        queryset = queryset.filter(matiere_id=subject_id)
    return queryset.exists()


def is_teacher_account(user):
    profile = getattr(user, 'profile', None)
    if profile is not None:
        return profile.role == 'teacher'
    return getattr(user, 'enseignant', None) is not None
