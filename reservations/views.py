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
from constance import config
import json
import os
import requests
import googlemaps
from sumup import Sumup
from sumup.checkouts import CreateCheckoutBody
import uuid
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
        "vehicule" : config.vehicle,
        "name" : config.driver,
        "messages" : [
        # request.POST,   # Données du formulaire
        # request.user,   # Utilisateur connecté
        # request.body,   # Corps brut JSON si fetch()
        # request.path,
        # TrajetForm(request.POST).get_context,
        ],
        "current_year" : current_year,
        'aller_retour':  False
    }

# Create your views here.
def index(request):
    context = context_init.copy()
    if request.method == "POST":
        form = TrajetForm(request.POST)
 
        if "btnConfirmer" not in request.POST and form.is_valid(): # Cas où on prévisualise
            trajet = form.save(commit=False)         
            date_retour = None

            if "aller_retour" in request.POST :
                # Récupère la date passée par le formulaire (format ISO local)
                date_retour_str = form.cleaned_data['date_retour'] #request.POST.get("date_retour", None)
                if date_retour_str:
                    dt = parse_datetime(date_retour_str)
                    if dt:
                        # rendre aware si nécessaire
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt)
                        date_retour = dt
                context['aller_retour'] = True
                
            data_trajet = evaluer_trajet(
                form.cleaned_data["adresse_depart"],
                form.cleaned_data["adresse_arrivee"],
                form.cleaned_data['date_aller'],
                date_retour
                )
            
            trajet.date_retour = date_retour
            trajet.distance_km, trajet.duree_min, trajet.price_euros = data_trajet['distance_km'], data_trajet['duree_min'], data_trajet['price_euros']  

            date_aller = form.cleaned_data['date_aller']
            date_aller_fin = date_aller + timedelta(minutes=data_trajet['duree_min'])

            if is_slot_available(id_agenda_creaneaux, date_aller, date_aller_fin) or not is_slot_available(id_agenda_reservations, date_aller, date_aller_fin):
                context['messages'].append("❌ L'horaire demandé n'est pas disponible pour réservation.\nLes créneaux de cette semaine sont les suivants :")
                for date in get_events_current_week(id_agenda_creaneaux):
                    context['messages'].append(date)
                context['messages'].append("\nSi vous vous trouvez déjà dans les créneaux de réservation, il se peut qu'une réservation ait déjà été prise le créneau demandé\n")
                context['form'] = form
                return render(request, "reservation.html", context)
            
            context['trajet'] = trajet

        elif "btnConfirmer" in request.POST and form.is_valid(): # Cas où on confirme la reservation
            trajet = form.save(commit=False)
            date_retour = None

            if "aller_retour" in request.POST :
                # Récupère et parse la date de retour avant sauvegarde
                date_retour_str = request.POST.get("date_retour", None)
                date_retour = None
                if date_retour_str:
                    dt = parse_datetime(date_retour_str)
                    if dt:
                        if timezone.is_naive(dt):
                            dt = timezone.make_aware(dt)
                        date_retour = dt
                context['aller_retour'] = True
                
            data_trajet = evaluer_trajet(
                form.cleaned_data["adresse_depart"],
                form.cleaned_data["adresse_arrivee"],
                form.cleaned_data['date_aller'],
                date_retour
                )
            
            checkout = create_checkout(sumpup_api_key,merchant_code_test, data_trajet['price_euros'], trajet)
            trajet.date_retour = date_retour
            trajet.distance_km = data_trajet['distance_km']
            trajet.duree_min = data_trajet['duree_min']
            trajet.price_euros = data_trajet['price_euros']  
            trajet.checkout_id = checkout.id
            trajet.checkout_status = checkout.status
            trajet.checkout_reference = checkout.checkout_reference

            trajet.save()

            request.session["checkout_id"] = checkout.id
            return redirect("contact/")
        
        else:
            messages.error(request, "Erreur dans le formulaire ❌")
    else:
        form = TrajetForm()

    context["form"] = form

    return render(request, "reservation.html", context)

def contact_form_view(request):
    context = context_init.copy()
    checkout_id = request.session.get("checkout_id")
    context["checkout_id"] = checkout_id
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

def paiement(request):
    context = context_init.copy()
    checkout_id = request.session.get("checkout_id")
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

def paiement_resultat(request):  # SUM UP WIDGET REDIRIGE ICI APRÈS PAIEMENT
    context = context_init.copy()

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
              f"durée : {paiement.duree_min} mins",
              f"prix : {paiement.price_euros}",
              f"client : NOM: {client.nom_client} PRENOM : {client.prenom_client}",
              f"contact : {paiement.telephone_client}",
              f"reference de paiement : {paiement.checkout_reference}"
        ]
        date_aller = paiement.date_aller
        date_aller_fin = paiement.date_aller + timedelta(minutes=paiement.duree_min)
        create_event(id_agenda_reservations,summary=f"VTC Reservation", start_dt=date_aller, end_dt=date_aller_fin, description='\n'.join(d_), location=paiement.adresse_depart )

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

    subject = "[SITE RESERVATION] Webhook triggered"
    content = f"""
    Le paiement pour la réservation {checkout_id} a le statut {status}.
    Requête : {request}, data = {data}
    Procéder au remboursement : 
        - Partiel : <<lien pour remboursement pariel - SumUp>>
        - Intégral : <<lien pour remboursement intégral - SumUp>>
    """
    send(mails, subject , content)

    return HttpResponse("OK", status=200)

def welcome(request):
    context = context_init.copy()

    return render(request, 'welcome.html', context)

def bon(request):
    checkout_id = request.session.get("checkout_id")
    current_trajet = Trajet.objects.get(checkout_id=checkout_id)
    current_contact = ContactClient.objects.filter(telephone_client=current_trajet.telephone_client).first()
    print(current_trajet)
    print(current_contact)

    date_aller = current_trajet.date_aller.strftime("%d/%m/%Y")
    time_aller = current_trajet.date_aller.strftime("%H:%M")
    asked_date = current_trajet.requested_at.strftime("%d/%m/%Y à %H:%M:%S")
    datetime_arrivee = current_trajet.date_aller + timezone.timedelta(minutes=current_trajet.duree_min)
    date_arrivee_estimee = datetime_arrivee.strftime("%d/%m/%Y")
    time_arrivee_estimee = datetime_arrivee.strftime("%H:%M")
    duree_human_readable = humaniser_duree(current_trajet.duree_min)
    commentaire_trajet = get_tarif_multiplier(current_trajet.date_aller.hour)['commentaire']

    context = {
        "asked_date":asked_date,
        "mode_reservation": "site web",
        "telephone":config.contact_phone,
        "siret": config.contact_siret,
        "mail" : config.contact_email,
        "adresse" : config.contact_address,
        "driver" : config.driver,
        "vehicle" : config.vehicle,
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
    }
    if current_trajet.date_retour != None:
        context["date_retour"] = current_trajet.date_retour.strftime("%d/%m/%Y")
        context["heure_retour"] = current_trajet.date_retour.strftime("%H:%M")
        context['aller_retour'] = "Oui"
    else:
        context['aller_retour'] = "Non"
    return render(request, 'template_bon_reservation.html', context)
