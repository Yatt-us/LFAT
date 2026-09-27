from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from .tenant import school_for_user

class CheckEcoleSubscriptionMiddleware:
    """
    Vérifie si l'école a une période d'essai active ou un abonnement valide.
    Bloque l'accès au système si la période d'essai est expirée et non payée.
    Compatible avec le site d'administration Django.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ⚙️ On ne bloque pas :
        # - les pages d'administration
        # - les pages de connexion / déconnexion
        # - la page de paiement
        exempt_paths = [
            reverse('login'),
            reverse('logout'),
            reverse('initier_paiement'),
            '/verifier/carte/',
            '/verifier/certificat/',
            '/verifier/document/',
            '/admin/login/',
            '/admin/',
        ]

        # ✅ Continuer normalement pour les pages exemptées
        if any(request.path.startswith(path) for path in exempt_paths):
            return self.get_response(request)

        if request.user.is_authenticated:
            ecole = school_for_user(request.user)

            if ecole:
                # L'accès dépend de l'état d'abonnement, pas d'un simple indicateur actif.
                if not ecole.peut_utiliser_systeme():
                    messages.warning(
                        request,
                        "L’accès à votre établissement est temporairement indisponible. "
                        "Consultez l’état de votre abonnement sur cette page."
                    )
                    return redirect('initier_paiement')

        # ✅ Sinon, continuer la requête normalement
        response = self.get_response(request)
        return response
