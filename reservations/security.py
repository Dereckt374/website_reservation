"""Protections anti-abus : limitation par IP, piège anti-robots, accès aux réservations, connexion admin.

Les compteurs sont stockés dans le cache Django (CACHES dans settings.py, sur disque pour être
partagé entre les workers Gunicorn). Aucune dépendance externe.
"""
from django.contrib.auth.signals import user_login_failed, user_logged_in
from django.core.cache import cache
from django.dispatch import receiver
from django.http import HttpResponse
from django.urls import reverse

# Nom du champ invisible du piège anti-robots (voir templates/_honeypot.html)
HONEYPOT_FIELD = "site_web"

# Limites par adresse IP : (nombre maximal, fenêtre en secondes)
LIMITES = {
    "contact":       (5, 3600),    # messages via le formulaire de contact
    "demande":       (5, 3600),    # demandes de réservation transmises (envoient des e-mails)
    "calcul":        (40, 3600),   # prévisualisations (appels OpenRouteService / Google Agenda)
    "admin_login":   (5, 900),     # échecs de connexion à l'admin avant blocage
}


def client_ip(request):
    """IP du visiteur derrière Nginx.

    Nginx doit transmettre l'IP réelle (proxy_set_header X-Real-IP $remote_addr; ou
    X-Forwarded-For $proxy_add_x_forwarded_for;). On prend la dernière entrée de
    X-Forwarded-For : c'est celle ajoutée par Nginx, le client ne peut pas la falsifier.
    """
    real_ip = request.META.get("HTTP_X_REAL_IP")
    if real_ip:
        return real_ip.strip()
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "inconnue")


def _cle(action, request):
    return f"limite:{action}:{client_ip(request)}"


def compter(request, action):
    """Incrémente le compteur de l'action pour cette IP et renvoie la nouvelle valeur."""
    _, fenetre = LIMITES[action]
    cle = _cle(action, request)
    cache.add(cle, 0, timeout=fenetre)   # crée le compteur (avec son expiration) s'il n'existe pas
    try:
        return cache.incr(cle)
    except ValueError:                   # expiré entre add() et incr()
        cache.set(cle, 1, timeout=fenetre)
        return 1


def limite_depassee(request, action, incrementer=True):
    """True si l'IP a dépassé la limite de l'action. Par défaut, compte la tentative en cours."""
    maximum, _ = LIMITES[action]
    valeur = compter(request, action) if incrementer else (cache.get(_cle(action, request)) or 0)
    return valeur > maximum


def est_robot(request):
    """Le champ invisible a été rempli : soumission automatique."""
    return bool(request.POST.get(HONEYPOT_FIELD, "").strip())


# ─── Accès aux documents d'une réservation (facture, bons PDF) ───────────────

def autoriser_reference(request, client_ref):
    """Mémorise en session que ce visiteur a lui-même créé la réservation client_ref."""
    refs = request.session.get("mes_reservations", [])
    if client_ref not in refs:
        refs.append(client_ref)
        request.session["mes_reservations"] = refs[-20:]


def acces_reference(request, client_ref):
    """Accès réservé à l'admin ou au visiteur qui a créé la réservation (même session)."""
    if request.user.is_authenticated and request.user.is_staff:
        return True
    return client_ref in request.session.get("mes_reservations", [])


# ─── Connexion à l'admin : blocage après trop d'échecs ───────────────────────

@receiver(user_login_failed)
def _echec_connexion(sender, credentials, request=None, **kwargs):
    if request is not None:
        compter(request, "admin_login")


@receiver(user_logged_in)
def _connexion_reussie(sender, request, user, **kwargs):
    cache.delete(_cle("admin_login", request))


class AdminLoginThrottleMiddleware:
    """Refuse les tentatives de connexion à l'admin d'une IP qui a trop échoué récemment."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path == reverse("admin:login"):
            maximum, _ = LIMITES["admin_login"]
            if (cache.get(_cle("admin_login", request)) or 0) >= maximum:
                return HttpResponse(
                    "Trop de tentatives de connexion. Réessayez dans 15 minutes.", status=429
                )
        return self.get_response(request)
