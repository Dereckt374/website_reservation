"""
Django settings for site_reservation project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv(dotenv_path='.venv/.env_prod')

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Sécurité de base ────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("django_secret_key")

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("django_allowed_hosts", "").split(",") if h.strip()]

# ─── HTTPS & Headers de sécurité (actifs uniquement hors DEBUG) ──────────────

if not DEBUG:
    # Redirection HTTP → HTTPS
    SECURE_SSL_REDIRECT = True

    # HSTS : impose HTTPS pendant 1 an
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Cookies sécurisés
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Headers de sécurité
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Cookies de session
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 3600          # 1 heure

CSRF_COOKIE_HTTPONLY = False       # doit rester accessible au JS (comportement Django par défaut)
CSRF_COOKIE_SAMESITE = "Lax"

# ─── Applications ────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'reservations',
    "constance",
    "constance.backends.database",
]

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"

CONSTANCE_CONFIG = {
    "hourly_cost": (30, "Taux horaire (€uros)"),
    "price_per_km": (1.5, "Prix par km en euros"),
    "evening_factor" : (20, "Majoration soirée (%)"),
    "night_factor" : (40, "Majoration nuit (%)"),
    "driver" : ("Stéphane", "Nom du chauffeur"),
    "vehicle" : ("Polestar 2 - Edition 2026, Véhicule Electrique, 5 places, coupé 4 portes", "Description du véhicule utilisé"),
    "vehicle_immatriculation" : ("HJ-663-EX", "Imatriculation du véhicule"),
    "contact_name": ("VTC MESLE Valence", "Nom de l'entreprise de réservation"),
    "contact_email": ("contact@mesle-entreprises.fr", "Email de contact pour les réservations"),
    "contact_phone": ("0644723935", "Numéro de téléphone de contact pour les réservations"),
    "contact_address_public": ("26000, VALENCE", "Adresse de contact pour les réservations"),
    "contact_address_private": ("38 Rue Albert Varnet, 26000, VALENCE", "Adresse de référence pour les calculs de trajets"),
    "contact_siret": ("435 222 401 00067", "Numéro de SIRET de l'entreprise"),
    "horaires": ("Disponibilité 24/24 7/7, sous réserve de disponibilité", "Horaires de réservation"),
    # Paramètres du slider Drive : voir .env_prod (slider_drive_folder_id, slider_excel_name, slider_drive_user)

    # ─── Informations légales (mentions légales, CGV, factures) ───────────────
    # Les valeurs "[À compléter …]" DOIVENT être renseignées dans l'admin avant la mise en ligne.
    "legal_form":            ("[À compléter : forme juridique, ex. EI / SASU au capital de … €]", "Forme juridique (+ capital si société). Une EI doit faire figurer « EI » après son nom."),
    "legal_owner":           ("[À compléter : nom et prénom de l'exploitant / représentant légal]", "Exploitant ou représentant légal"),
    "legal_address":         ("[À compléter : adresse du siège / domiciliation]", "Adresse du siège (obligatoire dans les mentions légales et sur les factures)"),
    "legal_registration":    ("[À compléter : RCS / RNE + ville]", "Immatriculation (RCS ou Registre national des entreprises)"),
    "legal_vat_mention":     ("TVA non applicable, art. 293 B du CGI", "Mention TVA (franchise en base) ou n° de TVA intracommunautaire si assujetti"),
    "legal_vtc_registry":    ("[À compléter : n° d'inscription au registre des exploitants VTC]", "N° d'inscription au registre des exploitants VTC (art. L3122-3 Code des transports)"),
    "legal_insurance":       ("[À compléter : assureur RC professionnelle transport de personnes + n° de contrat]", "Assurance responsabilité civile professionnelle"),
    "legal_publication_director": ("[À compléter : nom du directeur de la publication]", "Directeur de la publication du site"),
    "legal_host":            ("[À compléter : nom, adresse et téléphone de l'hébergeur]", "Hébergeur du site (art. 6 LCEN)"),
    "legal_mediator":        ("[À compléter : nom, adresse et site web du médiateur de la consommation]", "Médiateur de la consommation (art. L612-1 Code de la consommation)"),
    "legal_cancellation":    ("[À compléter : conditions d'annulation, ex. annulation gratuite jusqu'à 24 h avant la prise en charge, 50 % du prix au-delà, 100 % en cas d'absence du client]", "Conditions d'annulation affichées dans les CGV"),
    "legal_cgv_updated":     ("22/11/2026", "Date de dernière mise à jour des CGV / politique de confidentialité"),
}

# ─── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'site_reservation.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'reservations.context_processors.legal',
            ],
        },
    },
]

WSGI_APPLICATION = 'site_reservation.wsgi.application'

# ─── Base de données ─────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ─── Validation des mots de passe ────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── Internationalisation ─────────────────────────────────────────────────────

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# ─── Fichiers statiques ───────────────────────────────────────────────────────

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
