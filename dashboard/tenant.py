"""Utilities for resolving the school boundary of an authenticated account."""


def school_for_user(user):
    if not getattr(user, 'is_authenticated', False):
        return None
    profile = getattr(user, 'profile', None)
    teacher = getattr(user, 'enseignant', None)
    if profile is not None:
        if not profile.ecole_id:
            return None
        if teacher is not None and teacher.ecole_id != profile.ecole_id:
            return None
        return profile.ecole
    if teacher is not None and teacher.ecole_id:
        return teacher.ecole
    return None
