from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import TrajetForm, ContactClientForm
from .models import Trajet, ContactClient
from .utils import *
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.template.loader import render_to_string, get_template
from constance import config
import json
import os
import requests
import googlemaps
from sumup import Sumup
from sumup.checkouts import CreateCheckoutBody
from weasyprint import HTML, CSS
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env')

googlemaps_api_key = os.getenv("google_api_key")
sumpup_api_key = os.getenv("sumup_api_key")
merchant_code_test = os.getenv("merchant_code_test")
gmaps = googlemaps.Client(key=googlemaps_api_key)
current_year = datetime.now().year
mails = [os.getenv("email_destination")]
id_agenda_creaneaux = os.getenv("id_agenda_creaneaux")
id_agenda_reservations = os.getenv("id_agenda_reservations")

context_init = {
        "api_key" : googlemaps_api_key,
        "vehicle" : config.vehicle,
        "vehicle_immatriculation" : config.vehicle_immatriculation,
        "name" : config.driver,
        "messages" : [
        # request.POST,   # Données du formulaire
        # request.user,   # Utilisateur connecté
        # request.body,   # Corps brut JSON si fetch()
        # request.path,
        # TrajetForm(request.POST).get_context,
        ],
        "current_year" : current_year,
    }

# Create your views here.
def index(request):
    context = context_init.copy()
    if request.method == "POST":
        form = TrajetForm(request.POST)
 
        ## CAS PREVISUALISATION 
        if "btnConfirmer" not in request.POST and form.is_valid():
            trajet = form.save(commit=False) 

            context['trajet'] = trajet

        elif "btnConfirmer" in request.POST and form.is_valid(): # Cas où on confirme la reservation
            trajet = form.save(commit=False)
            checkout = create_checkout(sumpup_api_key,merchant_code_test, form.cleaned_data["price_euros"], trajet)
            trajet.checkout_id = checkout.id
            trajet.checkout_status = checkout.status
            trajet.checkout_reference = checkout.checkout_reference
            trajet.save()
            request.session["checkout_id"] = checkout.id
            return redirect('contact', client_ref=checkout.checkout_reference)

            return redirect(f"{trajet.checkout_reference}/contact/")
        
        else:
            messages.error(request, "Erreur dans le formulaire ❌")
    else:
        form = TrajetForm()

    context["form"] = form

    return render(request, "reservation.html", context)

def contact_form_view(request, client_ref):
    context = context_init.copy()
    checkout_id = request.session.get("checkout_id")
    context["checkout_id"] = checkout_id
    context["client_ref"] = client_ref
    if request.method == "POST":
        form = ContactClientForm(request.POST)
        context['form'] = form
        if form.is_valid():
            telephone = form.cleaned_data["telephone_client"]
            current_trajet = Trajet.objects.get(checkout_id=checkout_id)
            current_trajet.telephone_client = telephone
            current_trajet.save()
            form.save()
            return redirect("paiement/")
    else:
        context['form'] = ContactClientForm()

    return render(request, "contact.html", context=context)

def paiement(request, client_ref):
    context = context_init.copy()
    checkout_id = request.session.get("checkout_id")
    context["client_ref"] = client_ref

    if not checkout_id:
        messages.error(request, "Erreur dans la création du checkout ❌")
        return  render(request, "reservation.html", context)
    context["checkout_id"] = checkout_id
    with open(r".venv/temp_txt", "w") as f: f.write(checkout_id) 
    return render(request, "paiement.html", context=context)

def fct_test():
    # Simulation d'un webhook SUM UP pour les tests en local
    with open(r".venv/temp_txt", "r") as f: checkout_id = f.read().strip()
    url = "http://127.0.0.1:8000/webhook/"
    payload = {
        "id": checkout_id,
        "status": "PAID"
    }
    response = requests.post(url, json=payload)
    print(response.text)
    return checkout_id

def paiement_resultat(request, client_ref):  # SUM UP WIDGET REDIRIGE ICI APRÈS PAIEMENT
    context = context_init.copy()
    context["client_ref"] = client_ref
    # checkout_id = request.GET.get("checkout_id") # VRAI CAS
    checkout_id = fct_test() 
    
    paiement = Trajet.objects.get(checkout_id=checkout_id)  # ou .filter
    client = ContactClient.objects.filter(telephone_client=paiement.telephone_client).first()
    context["checkout_id"] = checkout_id
    context['checkout_status'] = paiement.checkout_status
    if paiement.checkout_status == "PAID":
        d_ = ["Reservation confirmée, voici les détails:",
              f"adresse de départ : {paiement.adresse_depart}",
              f"adresse d'arrivée : {paiement.adresse_arrivee}",
              f"distance : {paiement.distance_km} km",
              f"durée : {paiement.duree_min_aller} mins",
              f"prix : {paiement.price_euros} €",
              f"client : NOM: {client.nom_client} PRENOM : {client.prenom_client}",
              f"contact : {paiement.telephone_client}",
              f"reference de paiement : {paiement.checkout_reference}"
        ]
        date_aller = paiement.date_aller
        date_aller_fin = paiement.date_aller + timedelta(minutes=paiement.duree_min_aller)

        create_event(id_agenda_reservations,summary=f"VTC Reservation", start_dt=date_aller, end_dt=date_aller_fin, description='\n'.join(d_), location=paiement.adresse_depart )
        date_arrivee_estimee = date_aller_fin.strftime("%d/%m/%Y")
        time_arrivee_estimee = date_aller_fin.strftime("%H:%M")

        context_mail_client = {
            "reference_dossier" : client_ref, 
            "asked_date":paiement.requested_at.strftime("%d/%m/%Y à %H:%M:%S"),
            "mode_reservation": "Internet",
            "telephone":config.contact_phone ,
            "siret": config.contact_siret,
            "mail" : config.contact_email,
            "driver" : config.driver,
            "vehicle" : config.vehicle,
            "vehicle_immatriculation" : config.vehicle_immatriculation,
            "date_aller" : paiement.date_aller.strftime("%d/%m/%Y"),
            "heure_aller" : paiement.date_aller.strftime("%H:%M"),
            "date_arrivee_estimee" : date_arrivee_estimee,
            "heure_arrivee_estimee" : time_arrivee_estimee,
            "adresse_depart" : paiement.adresse_depart ,
            "adresse_arrivee" : paiement.adresse_arrivee,
            "temps_humain" : paiement.duree_min_aller,
            "nom_client" : client.nom_client,
        }
        ics_attachment = [{
            "filename": "reservation_aller.ics",
            "mimetype": "text/calendar",   # important
            "content": creer_ics(paiement.date_aller, date_aller_fin, f"Trajet VTC direction {paiement.adresse_arrivee}")
        }]
        
        if paiement.date_retour is not None:
            date_retour_fin = paiement.date_retour+timedelta(minutes=paiement.duree_min_retour)
            ics_attachment.append({
            "filename": "reservation_retour.ics",
            "mimetype": "text/calendar",   # important
            "content": creer_ics(paiement.date_retour, date_retour_fin, f"Trajet VTC direction {paiement.adresse_depart}") 
            })
            create_event(id_agenda_reservations,summary=f"VTC Reservation", start_dt=date_aller, end_dt=date_retour_fin, description='\n'.join(d_), location=paiement.adresse_depart )

        send_email_template(
            emails=mails,
            subject="[VTC Meslé] Reservation confirmée",
            template_name="template_mail_client.html",
            context=context_mail_client,
            attachments=ics_attachment
        )

        return render(request, "success.html", context=context)
    else:
        return render(request, "success.html", context=context)

@csrf_exempt
def sumup_webhook(request):
    try:
        data = json.loads(request.body)
    except Exception as e:
        return HttpResponse(f"Invalid JSON: {e}", status=400)
    
    checkout_id = data.get("id")
    status = data.get("status")  # PAID / FAILED / CANCELED

    if not checkout_id:
        return HttpResponse("Missing id", status=400)

    paiement = Trajet.objects.filter(checkout_id=checkout_id).first()

    if not paiement:
        return HttpResponse("Unknown checkout_id", status=404)
    

    paiement.checkout_status = status
    paiement.save()

    send_email_template(
        emails=mails,
        subject="[VTC] Reservation confirmée",
        template_name="template_mail_owner.html",
        context={"checkout_id": checkout_id,
                    "status" : status,
                    "request" : request,
                    "data" : data
                    }
        )
    
    return HttpResponse("OK", status=200)

def welcome(request):
    context = context_init.copy()

    return render(request, 'welcome.html', context)

def bon(request, client_ref):
    context = context_init.copy()
    context["client_ref"] = client_ref
    checkout_id = request.session.get("checkout_id")
    current_trajet = Trajet.objects.get(checkout_id=checkout_id)
    current_contact = ContactClient.objects.filter(telephone_client=current_trajet.telephone_client).first()
    date_aller = current_trajet.date_aller.strftime("%d/%m/%Y")
    time_aller = current_trajet.date_aller.strftime("%H:%M")
    asked_date = current_trajet.requested_at.strftime("%d/%m/%Y à %H:%M:%S")
    datetime_arrivee = current_trajet.date_aller + timezone.timedelta(minutes=current_trajet.duree_min_aller)
    date_arrivee_estimee = datetime_arrivee.strftime("%d/%m/%Y")
    time_arrivee_estimee = datetime_arrivee.strftime("%H:%M")
    duree_human_readable = humaniser_duree(current_trajet.duree_min_aller)
    commentaire_trajet = get_tarif_multiplier(current_trajet.date_aller.hour)['commentaire']

    context = {
        "reference_dossier" : client_ref,
        "asked_date":asked_date,
        "mode_reservation": "Internet",
        "telephone":config.contact_phone,
        "siret": config.contact_siret,
        "mail" : config.contact_email,
        "adresse" : config.contact_address,
        "driver" : config.driver,
        "vehicle" : config.vehicle,
        "vehicle_immatriculation" : config.vehicle_immatriculation,
        "date_aller": date_aller,
        "heure_aller": time_aller,
        "date_arrivee_estimee" : date_arrivee_estimee ,
        "heure_arrivee_estimee": time_arrivee_estimee,
        "adresse_depart" : current_trajet.adresse_depart,
        "adresse_arrivee" : current_trajet.adresse_arrivee,
        "prix"  : current_trajet.price_euros,
        "distance_km" : current_trajet.distance_km,
        "temps_humain" : duree_human_readable,
        "nom_client" : current_contact.nom_client,
        "prenom_client" : current_contact.prenom_client, 
        "telephone_client": current_contact.telephone_client,
        "email_client": current_contact.email_client,
        "passagers" : current_contact.passagers,
        "commentaire_client" : current_trajet.commentaire_client,
        "commenataire_trajet" : commentaire_trajet,
        "aller_retour" : current_trajet.type_trajet,
    }
    if current_trajet.date_retour != None:
        context["date_retour"] = current_trajet.date_retour.strftime("%d/%m/%Y")
        context["heure_retour"] = current_trajet.date_retour.strftime("%H:%M")
    
    pdf_name = f"bon_de_reservation_{client_ref}.pdf"
    html_string = render_to_string("template_bon_reservation.html", context)
    HTML(string=html_string).write_pdf(
    "reservations/output/"+pdf_name,
    stylesheets=[CSS("reservations/static/css/style_bon.css")]
)
    print("✅ Rapport généré")
    return render(request, 'template_bon_reservation.html', context)
