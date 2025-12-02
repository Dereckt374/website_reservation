from datetime import datetime, timedelta
import pytz
import zoneinfo
import uuid
import json
import os
import requests
import googlemaps
from django.utils import timezone
from django.template.loader import render_to_string
from constance import config
from sumup import Sumup
from sumup.checkouts import CreateCheckoutBody
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env')

googlemaps_api_key = os.getenv("google_api_key")
sumpup_api_key = os.getenv("sumup_api_key")
merchant_code_test = os.getenv("merchant_code_test")
gmaps = googlemaps.Client(key=googlemaps_api_key)
current_year = datetime.now().year

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
def get_merchant_code(api_key_application : str) -> str:
    client = Sumup(api_key=sumpup_api_key)
    merchant = client.merchant.get()
    merchant_code = merchant.merchant_profile.merchant_code
    return merchant_code
def create_checkout(api_key_application : str, merchant_code : str, price : float, description: str = "") -> str:
    client = Sumup(api_key=sumpup_api_key)
    checkout = client.checkouts.create(
        body=CreateCheckoutBody(
            amount=price,
            currency="EUR",
            checkout_reference=str(uuid.uuid4()).split('-')[0],
            merchant_code=merchant_code,
            description="description",
            redirect_url="http://127.0.0.1:8000/paiement/resultat/",
            return_url="http://127.0.0.1:8000/webhook/"
        )
    )

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
    """)
    service.quit()
def send_email_template(emails, subject, template_name, context=None, attachments=None):

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
        """)
    service.quit()
def get_service():
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    creds = service_account.Credentials.from_service_account_file(
        ".venv/service.json", scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)
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
def get_events_current_week(calendar_id, service_account_file=".venv/service.json"):
    """
    Récupère et affiche tous les événements de la semaine en cours (lundi → dimanche)
    en utilisant un service account Google Calendar.
    """

    service = get_service()
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

    service = get_service()

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
    service = get_service()

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

