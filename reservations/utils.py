from datetime import datetime, timedelta
import pytz
import uuid
import os
import requests
import googlemaps
from .models import Trajet, ContactClient
from django.utils import timezone
from django.template.loader import render_to_string
from django.conf import settings
from django.templatetags.static import static  # utile pour générer l'URL statique côté Python
from constance import config
from sumup import Sumup
from sumup.checkouts import CreateCheckoutBody
import random, string
# import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from weasyprint import HTML, CSS
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

site_domain = os.getenv("site_domain")
googlemaps_api_key = os.getenv("GOOGLE_MAPS_BACKEND_KEY")
sumup_api_key = os.getenv("sumup_api_key")
merchant_code_official = os.getenv("merchant_code_official")
gmaps = googlemaps.Client(key=googlemaps_api_key)
current_year = datetime.now().year
json_service_account_file = os.getenv("json_service_account_file")
base_url_sumup = "https://api.sumup.com"

logo_path = os.path.join(
    settings.STATIC_ROOT,
    "images/logo_SM_transp.png"
)


def get_tarif_multiplier(hour):
    """Renvoie le multiplicateur horaire selon la période (jour/soir/nuit)."""

    if 6 <= hour < 19:
        coef = 1.0
        commentaire = "Tarification de jour"
        return {"coef": coef, "commentaire":commentaire}
    elif 19 <= hour < 23:
        coef = 1.0 + (config.evening_factor/100)
        commentaire = "Tarification de soirée" 
        return {"coef": coef, "commentaire":commentaire}
    else:
        coef = 1.0 + (config.night_factor/100)
        commentaire = "Tarification de nuit"
        return {"coef": coef, "commentaire":commentaire} 
def evaluer_trajet(depart, arrivee, date_aller): #form.cleaned_data["adresse_depart"], form.cleaned_data["adresse_arrivee"], form.cleaned_data['date_aller']

    # Si la date est dans le passé, on la remplace par maintenant
    if date_aller < timezone.now(): date_aller = timezone.now()

    directions_result = gmaps.directions(depart, 
                                        arrivee,
                                         mode="driving",
                                         departure_time=date_aller)

    duree_min = round(directions_result[0]['legs'][0]['duration']['value']/60 ,1)
    distance_km = round(directions_result[0]['legs'][0]['distance']['value']/1000 ,1)

    time_multiplier = get_tarif_multiplier(date_aller.hour)['coef']
    price = round((distance_km * config.price_per_km + time_multiplier * config.hourly_cost * duree_min/60) ,1)    

    print(f"""
🔴 Fonction - EVALUER TRAJET 
    DATE ALLER : {date_aller}
    DEPART : {depart}
    ARRIVEE : {arrivee}
    DUREE : {duree_min} MIN
    DISTANCE : {distance_km} KM
    FACTEUR TEMPS : {time_multiplier}
    PRIX : {price} €
            """)
    
    return {"duree_min" :duree_min,"distance_km": distance_km, "price_euros":price}
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
        "https://www.googleapis.com/auth/drive.file"
        ]
    creds = service_account.Credentials.from_service_account_file(
        json_creds_file, scopes=SCOPES
    )
    if impersonated_user:
        creds_drive = creds.with_subject(impersonated_user)
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
    commentaire_trajet = get_tarif_multiplier(current_trajet.date_aller.hour)['commentaire']

    context = {
        'logo_image': logo_path,
        "reference_dossier" : current_trajet.checkout_reference, 
        "asked_date":asked_date_str,
        "mode_reservation": "Internet",
        "telephone":config.contact_phone ,
        "siret": config.contact_siret,
        "mail" : config.contact_email,
        "adresse" : config.contact_address,
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

def generate_invoice_number(client_ref):
    current_year = datetime.now().year
    invoice_number = f"{current_year}-FAC-{client_ref}"
    return invoice_number

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
        "address": config.contact_address,
        "country": "France",
        "siret": config.contact_siret,
        "vat_number": "TVA non applicable - Article 293B du code général des impôts",
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
        "number": generate_invoice_number(client_ref),
        "issue_date": timezone.now(),
        "items": [
            {
                "description": str(current_trajet),
                "date": current_trajet.date_aller,
                "quantity": 1,
                "unit_price_ht": current_trajet.price_euros,
            }
        
        ],
        "total_ttc": current_trajet.price_euros,
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

from googleapiclient.http import MediaFileUpload
import os


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

