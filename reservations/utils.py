from datetime import datetime, timedelta
import pytz
import uuid
import os
import requests
from .models import Trajet, ContactClient
from django.utils import timezone
from django.template.loader import render_to_string
from django.conf import settings
from django.templatetags.static import static  # utile pour générer l'URL statique côté Python
from constance import config
from sumup import Sumup
from sumup.checkouts import CreateCheckoutBody
import random, string
import unicodedata
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
# import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# from weasyprint import HTML, CSS
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

site_domain = os.getenv("site_domain")
ors_api_key = os.getenv("ORS_API_KEY")
sumup_api_key = os.getenv("sumup_api_key")
merchant_code_official = os.getenv("merchant_code_official")
current_year = datetime.now().year
json_service_account_file = os.getenv("json_service_account_file")
base_url_sumup = "https://api.sumup.com"

logo_path = os.path.join(
    settings.STATIC_ROOT,
    "images/logo_SM_transp.png"
)


# OpenRouteService : api.openrouteservice.org est coupé depuis le 24/11/2026 (410 Gone),
# remplacé par api.heigit.org (géocodage : /pelias/v1, itinéraires : /openrouteservice/v2).
ORS_BASE_URL = "https://api.heigit.org"


def est_heure_de_nuit(hour):
    """True si l'heure (locale) tombe dans la plage de nuit [night_start_hour ; night_end_hour[."""
    debut, fin = int(config.night_start_hour) % 24, int(config.night_end_hour) % 24
    if debut == fin:
        return False                      # plage vide : toujours tarif de jour
    if debut < fin:
        return debut <= hour < fin        # ex. 0 h → 6 h
    return hour >= debut or hour < fin    # ex. 19 h → 6 h (passe minuit)


def get_tarif_multiplier(hour):
    """Renvoie le multiplicateur horaire selon la période (jour/nuit)."""
    if est_heure_de_nuit(hour):
        return {"coef": 1.0 + (config.night_factor / 100), "commentaire": "Tarification de nuit"}
    return {"coef": 1.0, "commentaire": "Tarification de jour"}


def _geocoder_adresse(adresse):
    """Géocode une adresse via l'API ORS, retourne (lat, lon)."""
    url = f"{ORS_BASE_URL}/pelias/v1/search"
    params = {"api_key": ors_api_key, "text": adresse, "size": 1, "boundary.country": "FRA,MCO,BEL,CHE,LUX"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        raise ValueError(f"Adresse introuvable : {adresse}")
    lon, lat = features[0]["geometry"]["coordinates"]
    return float(lat), float(lon)


def evaluer_trajet(depart, arrivee, date_aller):
    if date_aller < timezone.now():
        date_aller = timezone.now()

    lat_dep, lon_dep = _geocoder_adresse(depart)
    lat_arr, lon_arr = _geocoder_adresse(arrivee)

    url = f"{ORS_BASE_URL}/openrouteservice/v2/directions/driving-car"
    headers = {"Authorization": ors_api_key, "Content-Type": "application/json"}
    body = {"coordinates": [[lon_dep, lat_dep], [lon_arr, lat_arr]]}
    resp = requests.post(url, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    summary = resp.json()["routes"][0]["summary"]

    duree_min = round(summary["duration"] / 60, 1)
    distance_km = round(summary["distance"] / 1000, 1)

    # Heure locale (Europe/Paris) : date_aller est stockée en UTC, sinon les majorations
    # de nuit s'appliqueraient avec 1 à 2 h de décalage par rapport aux tarifs annoncés.
    time_multiplier = get_tarif_multiplier(timezone.localtime(date_aller).hour)["coef"]
    price = round((distance_km * config.price_per_km + time_multiplier * config.hourly_cost * duree_min / 60), 1)

    print(f"""
🔴 Fonction - EVALUER TRAJET (ORS)
    DATE ALLER : {date_aller}
    DEPART : {depart}
    ARRIVEE : {arrivee}
    DUREE : {duree_min} MIN
    DISTANCE : {distance_km} KM
    FACTEUR TEMPS : {time_multiplier}
    PRIX : {price} €
            """)

    return {"duree_min": duree_min, "distance_km": distance_km, "price_euros": price}


def calculer_approche(adresse_depart, date_aller):
    """Distance/durée depuis config.contact_address_private jusqu'à l'adresse de départ."""
    try:
        result = evaluer_trajet(config.contact_address_private, adresse_depart, date_aller)
        return {"distance_km": result["distance_km"], "duree_min": result["duree_min"]}
    except Exception as e:
        print(f"⚠️ Erreur calcul approche : {e}")
        return {"distance_km": "N/A", "duree_min": "N/A"}


# ─── Forfaits hôtel ──────────────────────────────────────────────────────────
# Le tarif saisi dans l'Excel est le tarif de jour. La nuit, la même majoration que
# pour les trajets classiques (night_factor) s'applique à la totalité du forfait.

def prix_forfait(tarif, date_aller):
    """Prix d'un forfait à l'heure de prise en charge (heure locale), majorations incluses."""
    multiplier = get_tarif_multiplier(timezone.localtime(date_aller).hour)
    prix = (Decimal(str(tarif)) * Decimal(str(multiplier["coef"]))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"prix": prix, "coef": multiplier["coef"], "commentaire": multiplier["commentaire"]}


def grille_forfait(tarif):
    """Les deux prix d'un forfait (jour / nuit), pour l'affichage."""
    tarif = Decimal(str(tarif))
    nuit = (tarif * (1 + Decimal(str(config.night_factor)) / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"jour": tarif, "nuit": nuit}


def get_merchant_code(sumup_api_key : str) -> str:
    client = Sumup(api_key=sumup_api_key)
    merchant = client.merchant.get()
    merchant_code = merchant.merchant_profile.merchant_code
    return merchant_code

def create_checkout(sumup_api_key : str, merchant_code : str, price : float, description: str = "") -> str:
    client = Sumup(api_key=sumup_api_key)
    client_reference = ''.join(random.sample(string.ascii_uppercase * 6, 6))
    try:
        checkout = client.checkouts.create(
            body=CreateCheckoutBody(
                amount=price,
                currency="EUR",
                checkout_reference=client_reference,
                merchant_code=merchant_code,
                description=description,
                redirect_url=f"https://{site_domain}/{client_reference}/paiement/resultat/",
                return_url=f"https://{site_domain}/webhook-zRRjhnl549/"
            )
        )
    except Exception as e:
        print(e)
        if hasattr(e, "response"):
            print(e.response)
            print(e.response.text)
        raise
    

    print(f"""
🟠 Fonction - CREATE CHECKOUT
    Checkout ID: {checkout.id}
    Checkout Reference: {checkout.checkout_reference}
          """)


    return checkout


def old_create_checkout(api_key_application : str, merchant_code : str, price : float, description: str = "") -> str: 

    headers = {
        "Authorization": "Bearer " + api_key_application
    }

    payload = {
            "checkout_reference": "VTC" + str(int(datetime.now().timestamp())),
            "amount": price,
            "currency": "EUR",
            "merchant_code": merchant_code,
            "description": description
    }

    url = "https://api.sumup.com/v0.1/checkouts"

    response = requests.post(url, headers=headers, data=payload)

    return response.json()['id']
def send(emails, subject, content):
    
    service = smtplib.SMTP("smtp.gmail.com", 587)
    service.starttls()
    service.login(os.getenv("email_appli"), os.getenv("mdp_appli"))

    for email in emails:
        msg = MIMEMultipart()
        msg["From"] = os.getenv("email_appli")
        msg["To"] = email
        msg["Subject"] = subject

        # Texte encodé proprement
        msg.attach(MIMEText(content, "plain", "utf-8"))

        service.sendmail(os.getenv("email_appli"), email, msg.as_string())

    print(f"""
🟢 Fonction - SEND MAIL
    To : {emails}
    Subject : {subject}
    ✅ Mail sent
    """)
    service.quit()
def send_attachments(emails, subject, content, attachments=None):

    service = smtplib.SMTP("smtp.gmail.com", 587)
    service.starttls()
    service.login(os.getenv("email_appli"), os.getenv("mdp_appli"))

    for email in emails:
        msg = MIMEMultipart()
        msg["From"] = os.getenv("email_appli")
        msg["To"] = email
        msg["Subject"] = subject

        msg.attach(MIMEText(content, "plain", "utf-8"))

        # ============================
        #  Gestion des pièces jointes
        # ============================
        if attachments:
            for att in attachments:
                part = MIMEBase(*att["mimetype"].split("/"))
                part.set_payload(att["content"])
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att["filename"]}"'
                )
                msg.attach(part)

        service.sendmail(os.getenv("email_appli"), email, msg.as_string())

    print(f"""
🟢 Fonction - SEND MAIL ICS
    To : {emails}
    Subject : {subject}
    Attachments : {len(attachments) if attachments else 0}
    ✅ Mail sent
    """)
    service.quit()
def send_email_template(emails, subject, template_name, context=None, attachments=None):
    """
    Envoie un email HTML en utilisant un template Django. 
    ATTENTION, emails doit être une liste même pour un seul destinataire.
    """
    if context is None:
        context = {}
    # Informations légales disponibles dans tous les emails (pied de mail, lien CGV)
    from .legal import get_legal_context
    context = {"legal": get_legal_context(), "site_domain": site_domain, **context}

    # Rendu HTML avec le moteur de templates Django
    rendered_html = render_to_string(template_name, context)

    # fallback texte brut (optionnel mais recommandé)
    rendered_text = rendered_html.replace("<br>", "\n").replace("<p>", "\n").replace("</p>", "\n")

    service = smtplib.SMTP("smtp.gmail.com", 587)
    service.starttls()
    service.login(os.getenv("email_appli"), os.getenv("mdp_appli"))

    for email in emails:

        msg = MIMEMultipart("alternative")
        msg["From"] = os.getenv("email_appli")
        msg["To"] = email
        msg["Subject"] = subject

        # Texte brut
        msg.attach(MIMEText(rendered_text, "plain", "utf-8"))

        # HTML
        msg.attach(MIMEText(rendered_html, "html", "utf-8"))
        
        if attachments:
            for att in attachments:
                part = MIMEBase(*att["mimetype"].split("/"))
                part.set_payload(att["content"])
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att["filename"]}"'
                )
                msg.attach(part)
                
        service.sendmail(os.getenv("email_appli"), email, msg.as_string())
        print(f"""
🟢 Fonction - SEND MAIL HTML TEMPLATED
    To : {emails}
    Subject : {subject}
    Template : {template_name}
    Attachments : {len(attachments) if attachments else 0}
    ✅ Mail sent
        """)
    service.quit()
def get_services(json_creds_file=json_service_account_file,impersonated_user=None):
    services = {}
    SCOPES = [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/drive",
        ]
    creds = service_account.Credentials.from_service_account_file(
        json_creds_file, scopes=SCOPES
    )
    # Impersonation (with_subject) : uniquement avec Google Workspace + délégation domaine.
    # Sans utilisateur, le compte de service accède en son nom aux dossiers partagés avec lui.
    creds_drive = creds.with_subject(impersonated_user) if impersonated_user else creds
    services['drive'] = build("drive", "v3", credentials=creds_drive)

    services['calendar'] = build("calendar", "v3", credentials=creds)

    return services

def creer_ics(start_dt, end_dt, titre="Reservation"):
    """
    Génère une chaîne .ics pour un événement unique.
    start_dt et end_dt doivent être des datetime timezone-aware.
    """
    uid = uuid.uuid4()
    start_str = start_dt.strftime("%Y%m%dT%H%M%S")
    end_str   = end_dt.strftime("%Y%m%dT%H%M%S")

    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//SiteReservation//EN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{start_str}
DTSTART:{start_str}
DTEND:{end_str}
SUMMARY:{titre}
END:VEVENT
END:VCALENDAR
"""

    return ics
def get_week_date_range():
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz)

    # Lundi 00:00
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    # Dimanche 23:59:59
    week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # Format RFC3339 pour Google
    time_min = week_start.isoformat()
    time_max = week_end.isoformat()
    return week_start, week_end, time_min, time_max
def get_events_current_week(calendar_id):
    """
    Récupère et affiche tous les événements de la semaine en cours (lundi → dimanche)
    en utilisant un service account Google Calendar.
    """

    service = get_services()['calendar']
    week_start,week_end, time_min, time_max = get_week_date_range()

    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    if not events:
        print("Aucun événement cette semaine.")
        return

    # print(f"Événements du {week_start.date()} au {week_end.date()} :\n")
    event_list = []
    for event in events:
        start_dt = datetime.fromisoformat(event["start"].get("dateTime", event["start"].get("date")))
        end_dt  = datetime.fromisoformat(event["end"].get("dateTime", event["end"].get("date")))
        summary = event.get("summary", "(Sans titre)")

        # Conversion des dates en format 'xx/xx/xxxx - xx:xx à xx:xx'
        start_str = start_dt.strftime("%d/%m/%Y - %H:%M")
        end_str = end_dt.strftime("%d/%m/%Y - %H:%M")
        # print(f"- {summary}")
        # print(f"  Début : {start}")
        # print(f"  Fin   : {end}\n")
        if start_dt.date() == end_dt.date() : event_list.append(f"{start_str} à {end_dt.strftime('%H:%M')}")
        else : event_list.append(f"{start_str} au {end_str}")
    return event_list
def is_slot_available(calendar_id : str,
                    start_dt : datetime,
                    duration_min : int) -> bool:
    """
    Vérifie si un créneau est libre dans le calendrier id.
    start_dt est un datetime aware (CEST).
    duration_min est un int
    """
    end_dt = start_dt + timedelta(minutes=duration_min)

    service = get_services()['calendar']

    events = service.events().list(
        calendarId=calendar_id,
        timeMin=start_dt.isoformat(),
        timeMax=end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    items = events.get("items", [])

    print(f"""
⚪ Fonction - CHECK AVAILABILITIES
    date event : {start_dt.isoformat().split('+')[0]},
    duration event (min) : {duration_min},
    boolean test (True if available) : {len(items) == 0} 
    """)
    return len(items) == 0  # zéro signifie libre, car pas d'evenement présents : "créneau disponible"
def create_event(calendar_id, start_dt, end_dt, summary="Reservation", description="", location=""):
    service = get_services()['calendar']

    event_body = {
        "summary": summary,
        "description": description,
        "location": location,  # Ajout du champ "location"
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
    }
    event = service.events().insert(
        calendarId=calendar_id,
        body=event_body
    ).execute()
    
    print(f"""
🟣 Fonction - CREATE EVENT
    summary": {summary},
    description": {description},
    location": {location}, 
    start: {start_dt.isoformat()},
    date end: {end_dt.isoformat()},
    ✅ Envent created
    """)
    return event.get("id")
def humaniser_duree(duree_min: int) -> str:
    # Décomposition en base 60
    heures = duree_min // 60
    minutes = duree_min % 60
    
    segments = []
    
    if heures > 0:
        # Gestion du singulier/pluriel
        segments.append(f"{heures} heure" + ("s" if heures > 1 else ""))
    
    if minutes > 0:
        segments.append(f"{minutes} minute" + ("s" if minutes > 1 else ""))
    
    # Cas où la durée serait 0 min
    if not segments:
        return "0 minute"
    
    # Assemblage avec conjonction
    return " et ".join(segments)

def make_pdf(pdf_name, template_html, context, path_output, css=None):
    # from weasyprint import HTML, CSS
    html_string = render_to_string(template_html, context)
    HTML(string=html_string).write_pdf(
    os.path.join(path_output,pdf_name),
    base_url=settings.STATIC_ROOT,
    stylesheets=[CSS(css)] if css else None
    )
    output_path = os.path.join(path_output,pdf_name)
    print(f"""
🟦 Fonction - MAKE PDF
    PDF généré : {pdf_name},
    Template utilisé : {template_html},
    Chemin de sortie : {output_path}
    ✅ Rapport généré
    """)
    return output_path


def get_client_context(checkout_id):
    current_trajet = Trajet.objects.get(checkout_id=checkout_id)  # ou .filter
    client = ContactClient.objects.filter(telephone_client=current_trajet.telephone_client).last()

    asked_date_str = timezone.localtime(current_trajet.requested_at).strftime("%d/%m/%Y à %H:%M")
    date_aller_str = timezone.localtime(current_trajet.date_aller).strftime("%d/%m/%Y")
    time_aller_str = timezone.localtime(current_trajet.date_aller).strftime("%H:%M")
    datetime_arrivee_estimee_dt = current_trajet.date_aller + timedelta(minutes=current_trajet.duree_min_aller)
    date_arrivee_estimee_str = timezone.localtime(datetime_arrivee_estimee_dt).strftime("%d/%m/%Y")
    time_arrivee_estimee_str = timezone.localtime(datetime_arrivee_estimee_dt).strftime("%H:%M")
    duree_human_readable = humaniser_duree(current_trajet.duree_min_aller)
    commentaire_trajet = get_tarif_multiplier(timezone.localtime(current_trajet.date_aller).hour)['commentaire']

    context = {
        'logo_image': logo_path,
        "reference_dossier" : current_trajet.checkout_reference, 
        "asked_date":asked_date_str,
        "mode_reservation": "Internet",
        "telephone":config.contact_phone ,
        "siret": config.contact_siret,
        "mail" : config.contact_email,
        "adresse" : config.legal_address,
        "driver" : config.driver,
        "vehicle" : config.vehicle,
        "vehicle_immatriculation" : config.vehicle_immatriculation,
        "date_aller" : date_aller_str,
        "heure_aller" : time_aller_str,
        "date_arrivee_estimee" : date_arrivee_estimee_str,
        "heure_arrivee_estimee" : time_arrivee_estimee_str,
        "adresse_depart" : current_trajet.adresse_depart ,
        "adresse_arrivee" : current_trajet.adresse_arrivee,
        "prix"  : current_trajet.price_euros,
        "distance_km" : current_trajet.distance_km,
        "duree_min" : current_trajet.duree_min_aller,
        "temps_humain" : duree_human_readable,
        "nom_client" : client.nom_client,
        "prenom_client" : client.prenom_client, 
        "telephone_client": client.telephone_client,
        "email_client": client.email_client,
        "passagers" : client.passagers,
        "commentaire_client" : current_trajet.commentaire_client,
        "commenataire_trajet" : commentaire_trajet,
        "aller_retour" : current_trajet.type_trajet,
    }
    if current_trajet.date_retour != None:
        date_retour_str = timezone.localtime(current_trajet.date_retour).strftime("%d/%m/%Y")
        time_retour_str = timezone.localtime(current_trajet.date_retour).strftime("%H:%M")
        datetime_arrivee_estimee_dt = current_trajet.date_retour + timedelta(minutes=current_trajet.duree_min_retour)
        date_arrivee_estimee_str = timezone.localtime(datetime_arrivee_estimee_dt).strftime("%d/%m/%Y")
        time_arrivee_estimee_str = timezone.localtime(datetime_arrivee_estimee_dt).strftime("%H:%M")
        context["date_retour"] = date_retour_str
        context["heure_retour"] = time_retour_str
        context["date_arrivee_estimee_retour"] = date_arrivee_estimee_str
        context["heure_arrivee_estimee_retour"] = time_arrivee_estimee_str
    return context

def generate_invoice_number(trajet):
    """
    Attribue (une seule fois) un numéro de facture chronologique et continu : AAAA-0001, AAAA-0002…
    Une référence aléatoire n'est pas conforme (art. 242 nonies A, annexe II du CGI).
    """
    from django.db import transaction
    if trajet.numero_facture:
        return trajet.numero_facture
    year = timezone.localtime().year
    with transaction.atomic():
        last = (Trajet.objects.select_for_update()
                .filter(numero_facture__startswith=f"{year}-")
                .order_by("-numero_facture")
                .values_list("numero_facture", flat=True)
                .first())
        seq = int(last.split("-")[1]) + 1 if last else 1
        trajet.numero_facture = f"{year}-{seq:04d}"
        trajet.save(update_fields=["numero_facture"])
    return trajet.numero_facture

def get_welcome_context():
    context = {
    'front_image': static('images/fond3_2.jpg'),
    'logo_image': static('images/logo_SM_transp.png'),
    'company': {
        'name': config.contact_name,
        'tagline': 'Services de chauffeur haut de gamme',
        'description': "Profitez de votre transport en toute tranquilité, avec un véhicule haut de gamme et une qualité de service inégalée."
    },
    
    'contact': {
        'phone': config.contact_phone,
        'email': config.contact_email,
        'address': config.contact_address
    },
    
    'highlights': [
        {
            'id': 1,
            'title': 'Professional Drivers',
            'description': 'Experienced, licensed chauffeurs with impeccable service standards and local expertise.',
            'icon': 'user-check'
        },
        {
            'id': 2,
            'title': 'Punctuality Guaranteed',
            'description': 'We value your time. On-time pickups and efficient routes to ensure timely arrivals.',
            'icon': 'clock'
        },
        {
            'id': 3,
            'title': 'Luxury Fleet',
            'description': 'Premium vehicles including Mercedes S-Class, BMW 7 Series, and luxury SUVs.',
            'icon': 'car'
        },
        {
            'id': 4,
            'title': '24/7 Availability',
            'description': 'Round-the-clock service for airport transfers, business trips, and special events.',
            'icon': 'phone-call'
        },
        {
            'id': 5,
            'title': 'Comfort & Safety',
            'description': 'Impeccably maintained vehicles with premium amenities and comprehensive insurance.',
            'icon': 'shield-check'
        },
        {
            'id': 6,
            'title': 'Discretion Assured',
            'description': 'Professional and confidential service tailored to your privacy requirements.',
            'icon': 'lock'
        }
    ],
    
    'vehicles': [
        {
            'id': 1,
            'name': config.vehicle,
            'category': 'Berline de luxe électrique',
            'passengers': '4 passengers',
            'luggage': '4 bagages cabine',
            'image': static('images/fond6_2.jpeg'),
            'features': ['Leather seats', 'Climate control', 'WiFi', 'Bottled water']
        },
    ],
    
    'services': [
        'Airport Transfers',
        'Business Transportation',
        'Special Events',
        'City Tours',
        'Long Distance Travel',
        'Corporate Accounts'
    ],

    'driver_image': 'https://images.unsplash.com/photo-1607642857266-88f5f03e66c6'
    }
    return context

def get_facture_context(client_ref):
    current_trajet = Trajet.objects.get(checkout_reference=client_ref)
    client = ContactClient.objects.filter(telephone_client=current_trajet.telephone_client).last()
    context_facture = {
    'logo_image': logo_path,
    "company": {
        "name": config.contact_name,
        "legal_form": config.legal_form,
        "address": config.legal_address,
        "country": "France",
        "siret": config.contact_siret,
        "registration": config.legal_registration,
        "vtc_registry": config.legal_vtc_registry,
        "vat_number": config.legal_vat_mention,
        "email": config.contact_email,
        "phone": config.contact_phone,
    },

    "client": {
        "full_name": client.nom_client + " " + client.prenom_client,
        "address": client.client_adress,
        "phone": client.telephone_client,
        "email": client.email_client,
    },

    "reservation": {
        "reference": current_trajet.checkout_reference,
        "date": current_trajet.requested_at,
        "departure": current_trajet.adresse_depart,
        "arrival": current_trajet.adresse_arrivee,
    },

    "invoice": {
        "number": generate_invoice_number(current_trajet),
        "issue_date": timezone.localtime().strftime("%d/%m/%Y"),
        "items": [
            {
                "description": (
                    f"Transport de personnes en VTC ({current_trajet.type_trajet}) : "
                    f"{current_trajet.adresse_depart} → {current_trajet.adresse_arrivee}, "
                    f"{current_trajet.distance_km} km"
                ),
                "date": timezone.localtime(current_trajet.date_aller).strftime("%d/%m/%Y %H:%M"),
                "quantity": 1,
                "unit_price": current_trajet.price_euros,
            }
        ],
        "total": current_trajet.price_euros,
    },

    "payment": {
        "method": "Carte bancaire",
        "status": current_trajet.checkout_status,
        "date": "",
        "reference": current_trajet.checkout_id,
    }
}
    return context_facture
            


def get_transaction_id(checkout_id: str, sumup_api_key: str) -> str | None:
    """
    Récupère un checkout SumUp via son id_checkout
    et renvoie le transaction_id associé.
    """
    client = Sumup(api_key=sumup_api_key)
    # Récupération du checkout
    checkout = client.checkout.get(checkout_id)

    # Même logique que ci-dessus
    if checkout.transaction_id:
        return checkout.transaction_id

    if checkout.transactions:
        return checkout.transactions[0].id

    return None


def partial_refund_sumup(transaction_id: str, original_amount: float, ratio: float = 0.8):
    """Remboursement partiel (80% par défaut)."""
    refund_amount = round(original_amount * ratio, 2)

    url = f"{base_url_sumup}/v0.1/me/refund/{transaction_id}"
    headers = {
        "Authorization": f"Bearer {sumup_api_key}",
        "Content-Type": "application/json"
    }

    # response = requests.post(url, headers=headers, json={"amount": refund_amount})
    response = ''

    print(f"""
🟥 Fonction - PARTIAL REFUND
    Remboursement partiel :
    Transaction ID : {transaction_id}
    Montant original : {original_amount} EUR
    Ratio de remboursement : {ratio*100:.2f}%
    Montant remboursé : {refund_amount} EUR
    URL : {url}
    HTTP response : {response.status_code}
    🚫 Refund not processed (DISABLED)
    """)

    # if response.status_code == 204:
    #     print(f"✔ Remboursement effectué {ratio*100:.2f}% OK")
    # else:
    #     print(f"Echec du remboursement : {response.text}")

    return response


def full_refund_sumup(transaction_id: str):
    """Remboursement total."""
    url = f"{base_url_sumup}/v0.1/me/refund/{transaction_id}"
    headers = {"Authorization": f"Bearer {sumup_api_key}"}
    response = ''
    # response = requests.post(url, headers=headers)

    print(f"""
🟥 Fonction - FULL REFUND
    Remboursement partiel :
    Transaction ID : {transaction_id}
    URL : {url}
    HTTP response : {response.status_code}
    🚫 Refund not processed (DISABLED)
    """)

    # if response.status_code == 204:
    #     print("✔ Remboursement total OK")
    # else:
    #     print(f"Echec du remboursement : {response.text}")
    
    return response

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import json
import openpyxl
import os
from PIL import Image


# Dimensions cibles pour le redimensionnement des images du slider
SLIDER_TARGET_W = 1600
SLIDER_TARGET_H = 900


def _redimensionner_image(data: bytes, filename: str) -> bytes:
    """
    Redimensionne une image en 1600×900 px (cover + crop centré).
    Retourne les bytes de l'image redimensionnée au format d'origine.
    """
    ext = os.path.splitext(filename)[1].lower()
    fmt_map = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".gif": "GIF"}
    fmt = fmt_map.get(ext, "JPEG")

    img = Image.open(io.BytesIO(data)).convert("RGB")

    # Scale pour couvrir la cible (cover)
    scale = max(SLIDER_TARGET_W / img.width, SLIDER_TARGET_H / img.height)
    new_w = int(img.width  * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Crop centré
    left = (new_w - SLIDER_TARGET_W) // 2
    top  = (new_h - SLIDER_TARGET_H) // 2
    img  = img.crop((left, top, left + SLIDER_TARGET_W, top + SLIDER_TARGET_H))

    buf = io.BytesIO()
    save_kwargs = {"quality": 88, "optimize": True} if fmt == "JPEG" else {}
    img.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def _telecharger_fichier_drive(drive, file_id: str) -> bytes:
    """Télécharge un fichier Drive par son ID et retourne ses bytes."""
    request = drive.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def _lister_fichiers_drive(drive, folder_id: str) -> list:
    """Liste tous les fichiers (non supprimés) d'un dossier Drive."""
    result = drive.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)",
        pageSize=100,
    ).execute()
    return result.get("files", [])


def _charger_excel_slider(drive, excel_files: list, excel_name: str):
    """Télécharge l'Excel du dossier slider (celui nommé excel_name, sinon le premier trouvé)."""
    excel_match = next((f for f in excel_files if f["name"] == excel_name), None) or \
                  (excel_files[0] if excel_files else None)
    if not excel_match:
        return None
    excel_data = _telecharger_fichier_drive(drive, excel_match["id"])
    return openpyxl.load_workbook(io.BytesIO(excel_data), data_only=True)


def _onglet_slider(wb):
    """Onglet des textes du slider : le premier onglet qui n'est pas celui des forfaits."""
    return next((ws for ws in wb.worksheets if "forfait" not in _normaliser(ws.title)), wb.worksheets[0])


def _normaliser(texte) -> str:
    """Minuscules sans accents, pour comparer des en-têtes saisis à la main."""
    texte = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return texte.strip().lower()


def _parser_tarif(valeur) -> Decimal:
    """Accepte 45, 45.5, « 45,50 », « 45 € »."""
    if isinstance(valeur, (int, float)):
        return Decimal(str(valeur)).quantize(Decimal("0.01"))
    texte = str(valeur or "").replace("€", "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(texte).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"tarif illisible « {valeur} »")


def sync_forfaits_from_drive() -> dict:
    """
    Synchronise les forfaits hôtel depuis l'onglet « Forfaits » de l'Excel du slider.

    Colonnes attendues (en-têtes en ligne 1, accents et majuscules indifférents) :
      - « Départ », « Arrivée », « Tarif »            : obligatoires (nom affiché + tarif de jour TTC)
      - « Adresse départ », « Adresse arrivée »       : facultatives. Si absentes ou vides,
        le nom est utilisé pour le calcul d'itinéraire (ex. « Novotel Valence Sud »).
      - « Ordre »                                     : facultative, ordre d'affichage.
    Le temps de trajet et la distance sont calculés pour chaque ligne (OpenRouteService).
    Les forfaits existants sont remplacés par le contenu de l'onglet.
    """
    from django.db import transaction
    from .models import Forfait

    drive_user = os.getenv("slider_drive_user", "")
    folder_id  = os.getenv("slider_drive_folder_id", "").strip()
    excel_name = os.getenv("slider_excel_name", "").strip()
    if not folder_id:
        raise ValueError("Renseignez 'slider_drive_folder_id' dans .venv/.env_prod puis redémarrez le serveur.")

    drive = get_services(impersonated_user=(drive_user or "").strip() or None)["drive"]
    files = _lister_fichiers_drive(drive, folder_id)
    excel_files = [f for f in files if f["name"].lower().endswith((".xlsx", ".xls"))]
    wb = _charger_excel_slider(drive, excel_files, excel_name)
    if wb is None:
        raise ValueError("Aucun fichier Excel trouvé dans le dossier Drive du slider.")

    ws = next((w for w in wb.worksheets if "forfait" in _normaliser(w.title)), None)
    if ws is None:
        raise ValueError("Aucun onglet « Forfaits » dans l'Excel du slider.")

    headers = [_normaliser(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]

    def _col(*mots, sans=None):
        for i, h in enumerate(headers):
            if all(m in h for m in mots) and not (sans and sans in h):
                return i
        return None

    col_nom_dep  = _col("depart", sans="adresse")
    col_nom_arr  = _col("arriv", sans="adresse")
    col_adr_dep  = _col("adresse", "depart")
    col_adr_arr  = _col("adresse", "arriv")
    col_tarif    = _col("tarif") if _col("tarif") is not None else _col("prix")
    col_ordre    = _col("ordre")
    if None in (col_nom_dep, col_nom_arr, col_tarif):
        raise ValueError("L'onglet « Forfaits » doit contenir les colonnes « Départ », « Arrivée » et « Tarif ».")

    def _cell(row, idx):
        if idx is None or idx >= len(row) or row[idx] is None:
            return ""
        return str(row[idx]).strip()

    forfaits, erreurs = [], []
    for num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        nom_dep, nom_arr = _cell(row, col_nom_dep), _cell(row, col_nom_arr)
        if not nom_dep and not nom_arr:
            continue  # ligne vide
        try:
            if not nom_dep or not nom_arr:
                raise ValueError("départ ou arrivée manquant")
            tarif   = _parser_tarif(row[col_tarif] if col_tarif < len(row) else None)
            adr_dep = _cell(row, col_adr_dep) or nom_dep
            adr_arr = _cell(row, col_adr_arr) or nom_arr
            trajet  = evaluer_trajet(adr_dep, adr_arr, timezone.now())
            ordre_txt = _cell(row, col_ordre)
            forfaits.append(Forfait(
                nom_depart=nom_dep, adresse_depart=adr_dep,
                nom_arrivee=nom_arr, adresse_arrivee=adr_arr,
                tarif=tarif,
                duree_min=round(trajet["duree_min"]),
                distance_km=Decimal(str(trajet["distance_km"])),
                ordre=int(float(ordre_txt)) if ordre_txt else num,
            ))
        except Exception as e:
            erreurs.append(f"ligne {num} ({nom_dep or '?'} → {nom_arr or '?'}) : {e}")

    if not forfaits and erreurs:
        raise ValueError("aucun forfait valide — " + " ; ".join(erreurs))

    with transaction.atomic():
        Forfait.objects.all().delete()
        Forfait.objects.bulk_create(forfaits)

    print(f"""
🏨 Fonction - SYNC FORFAITS DRIVE
    Forfaits importés : {len(forfaits)}
    Erreurs : {len(erreurs)}
    """)
    return {"forfaits_count": len(forfaits), "erreurs": erreurs}


def sync_slider_from_drive() -> dict:
    """
    Synchronise le slider depuis Google Drive :
      - Télécharge les images du dossier Drive → static/images/landing_page/
      - Télécharge l'Excel de mapping nom_image→texte → slider_texts.json
    Retourne un dict de résultat.
    """
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

    # Paramètres lus dans .venv/.env_prod
    drive_user  = os.getenv("slider_drive_user", "")
    folder_id   = os.getenv("slider_drive_folder_id", "").strip()
    excel_name  = os.getenv("slider_excel_name", "").strip()

    if not folder_id:
        raise ValueError("Renseignez 'slider_drive_folder_id' dans .venv/.env_prod puis redémarrez le serveur.")

    drive = get_services(impersonated_user=(drive_user or "").strip() or None)["drive"]

    # 1. Lister le contenu du dossier
    files = _lister_fichiers_drive(drive, folder_id)
    images       = [f for f in files if any(f["name"].lower().endswith(ext) for ext in IMAGE_EXTENSIONS)]
    excel_files  = [f for f in files if f["name"].lower().endswith((".xlsx", ".xls"))]

    # 2. Dossier local de destination
    img_dir = os.path.join(settings.MEDIA_ROOT, "reservations", "static", "images", "landing_page")
    os.makedirs(img_dir, exist_ok=True)

    # 3. Supprimer les anciennes images locales
    for existing in os.listdir(img_dir):
        if any(existing.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
            os.remove(os.path.join(img_dir, existing))

    # 4. Télécharger et redimensionner les nouvelles images
    downloaded = []
    for img_file in images:
        data = _telecharger_fichier_drive(drive, img_file["id"])
        try:
            data = _redimensionner_image(data, img_file["name"])
            print(f"  🖼️  Redimensionnée : {img_file['name']} → {SLIDER_TARGET_W}×{SLIDER_TARGET_H}px")
        except Exception as e:
            print(f"  ⚠️  Redimensionnement échoué pour {img_file['name']} : {e} (image conservée telle quelle)")
        with open(os.path.join(img_dir, img_file["name"]), "wb") as f:
            f.write(data)
        downloaded.append(img_file["name"])
        print(f"  ✅ Image sauvegardée : {img_file['name']}")

    # 5. Télécharger et parser l'Excel de mapping
    texts_map = {}
    wb = _charger_excel_slider(drive, excel_files, excel_name)

    if wb is not None:
        ws = _onglet_slider(wb)

        # Lecture de l'en-tête pour localiser les colonnes dynamiquement
        headers = [str(c.value).strip().lower() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
        col_image  = next((i for i, h in enumerate(headers) if "image" in h or "nom" in h), 0)
        col_texte  = next((i for i, h in enumerate(headers) if "texte" in h or "text" in h), 1)
        col_ordre  = next((i for i, h in enumerate(headers) if "ordre" in h or "order" in h), None)

        for row in ws.iter_rows(min_row=2, values_only=True):
            nom = row[col_image] if len(row) > col_image else None
            texte = row[col_texte] if len(row) > col_texte else None
            if not nom or not texte:
                continue
            entry = {"texte": str(texte).strip()}
            if col_ordre is not None and len(row) > col_ordre and row[col_ordre] is not None:
                try:
                    entry["ordre"] = int(row[col_ordre])
                except (ValueError, TypeError):
                    pass
            texts_map[str(nom).strip()] = entry

        print(f"  ✅ Excel parsé : {len(texts_map)} entrée(s)")
    else:
        print("  ⚠️  Aucun fichier Excel trouvé dans le dossier Drive.")

    # 6. Sauvegarder le mapping JSON localement
    json_path = os.path.join(img_dir, "slider_texts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(texts_map, f, ensure_ascii=False, indent=2)

    result = {
        "images_count": len(downloaded),
        "texts_count":  len(texts_map),
        "images":       downloaded,
    }
    print(f"""
🖼️  Fonction - SYNC SLIDER DRIVE
    Dossier Drive : {folder_id}
    Images : {len(downloaded)}
    Textes : {len(texts_map)}
    ✅ Sync terminée
    """)
    return result


def upload_file_to_drive(
    local_path: str,
    drive_folder_name: str,
    inpersonated_user: str,
) -> str:
    """
    Upload un fichier dans le Drive de l'utilisateur impersonné,
    dans le dossier spécifié (créé s'il n'existe pas).

    :param local_path: chemin local du fichier
    :param drive_folder_name: nom du dossier Drive cible
    :return: file_id Google Drive
    """

    if not os.path.isfile(local_path):
        raise FileNotFoundError(local_path)

    drive = get_services(impersonated_user=inpersonated_user)["drive"]

    try:
        # 1️⃣ Recherche du dossier DANS LE DRIVE UTILISATEUR
        query = (
            f"name='{drive_folder_name}' and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )

        res = drive.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
        ).execute()

        if res.get("files"):
            folder_id = res["files"][0]["id"]
        else:
            # 2️⃣ Création du dossier dans le Drive utilisateur
            folder = drive.files().create(
                body={
                    "name": drive_folder_name,
                    "mimeType": "application/vnd.google-apps.folder",
                },
                fields="id",
            ).execute()
            folder_id = folder["id"]

        # 3️⃣ Upload du fichier
        media = MediaFileUpload(
            local_path,
            resumable=True,
        )

        uploaded = drive.files().create(
            body={
                "name": os.path.basename(local_path),
                "parents": [folder_id],
            },
            media_body=media,
            fields="id",
        ).execute()


        print(f"""
🟫 Fonction - UPLOAD FILE IN G DRIVE
    File ID: {uploaded["id"]}
    Local path : {local_path}
    Drive targeted folder : {drive_folder_name}
    ✅ File uploaded
            """)

        return uploaded["id"]

    except HttpError as e:
        # Diagnostic clair en logs
        raise RuntimeError(
            f"Google Drive upload failed ({e.resp.status}): {e.error_details}"
        ) from e

