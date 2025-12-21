from datetime import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import TrajetForm, ContactClientForm, AdressClientForm
from .models import Trajet, ContactClient
from .utils import *
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
import json
from time import sleep
import os
import requests
import googlemaps
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

site_domain = os.getenv("site_domain")
googlemaps_api_key = os.getenv("google_api_key")
sumup_api_key = os.getenv("sumup_api_key")
merchant_code_official = os.getenv("merchant_code_official")
gmaps = googlemaps.Client(key=googlemaps_api_key)
current_year = datetime.now().year
id_agenda_creaneaux = os.getenv("id_agenda_creaneaux")
id_agenda_reservations = os.getenv("id_agenda_reservations")

context_init = {
        "api_key" : googlemaps_api_key,
        "current_year" : current_year,
    }
def index(request):
    context = context_init.copy()
    context['name'] = config.driver
    context['vehicle_immatriculation'] = config.vehicle_immatriculation
    context['vehicle'] = config.vehicle
    if request.method == "POST":
        form = TrajetForm(request.POST)
 
        if "btnConfirmer" not in request.POST and form.is_valid():
            trajet = form.save(commit=False) 

            context['trajet'] = trajet

        elif "btnConfirmer" in request.POST and form.is_valid(): # Cas où on confirme la reservation
            trajet = form.save(commit=False)
            checkout = create_checkout(sumup_api_key, merchant_code_official, form.cleaned_data["price_euros"], description=str(trajet))
            trajet.checkout_id = checkout.id
            trajet.checkout_status = checkout.status
            trajet.checkout_reference = checkout.checkout_reference
            trajet.save()
            request.session["checkout_id"] = checkout.id
            return redirect('contact', client_ref=checkout.checkout_reference)
                
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
        messages.error(request, "❌ Erreur dans la création du checkout, retour vers la page de réservation")
        return  render(request, "reservation.html", context)
    context["checkout_id"] = checkout_id
    with open(r".venv/temp_txt", "w") as f: f.write(checkout_id) 
    return render(request, "paiement.html", context=context)

def fct_test():
    # Simulation d'un webhook SUM UP pour les tests en local
    with open(r".venv/temp_txt", "r") as f: checkout_id = f.read().strip()
    url = f"{site_domain}/webhook/"
    payload = {
        "id": checkout_id,
        "status": "PAID" #"FAILED"
    }
    response = requests.post(url, json=payload)
    print(response.text)
    return checkout_id

def paiement_resultat(request, client_ref):  # SUM UP WIDGET REDIRIGE ICI APRÈS PAIEMENT
    context = context_init.copy()
    context["client_ref"] = client_ref
    # checkout_id = request.GET.get("checkout_id") # VRAI CAS
    # paiement = Trajet.objects.get(checkout_id=checkout_id)
    paiement = Trajet.objects.get(checkout_reference=client_ref)
    checkout_id = paiement.checkout_id
    client_name = ContactClient.objects.filter(telephone_client=paiement.telephone_client).last()
    context["client_name"] = client_name.prenom_client
    context['email_client'] = client_name.email_client
    tries = 0
    while tries < 5 :
        if paiement.checkout_status == "PAID":

            context = context 
            return render(request, "success.html", context=context)
        else:
            sleep(2)
            paiement = Trajet.objects.get(checkout_id=checkout_id)  # ou .filter
            tries += 1
    return render(request, "echec.html", context=context)

@csrf_exempt
def sumup_webhook(request):
    try:
        data = json.loads(request.body)
    except Exception as e:
        return HttpResponse(f"Invalid JSON: {e}", status=400)
    
    send(["virgil.mesle@gmail.com"], "Webhook reçu", f"Webhook reçu avec les données : {data}")

    checkout_id = data.get("id")
    if not checkout_id:
        return HttpResponse("Missing id", status=400)
    
    status = data.get("status")  # PAID / FAILED / CANCELED

    if not status:
        return HttpResponse("Missing status", status=400)

    paiement = Trajet.objects.filter(checkout_id=checkout_id).last()

    if not paiement:
        return HttpResponse("Unknown checkout_id", status=404)
    
    paiement.checkout_status = status
    paiement.save()

    datetime_arrivee_estimee_dt = paiement.date_aller + timedelta(minutes=paiement.duree_min_aller)
    context_client = get_client_context(checkout_id)

    d_ = ["Reservation confirmée, voici les détails:"]
    d_.append("\n".join(f"{k} : {v}" for k, v in context_client.items()))

    create_event(id_agenda_reservations,summary=f"VTC Reservation", start_dt=paiement.date_aller, end_dt=datetime_arrivee_estimee_dt, description='\n'.join(d_), location=paiement.adresse_depart )

    ics_attachment = [{
        "filename": "reservation_aller.ics",
        "mimetype": "text/calendar",
        "content": creer_ics(paiement.date_aller, datetime_arrivee_estimee_dt, f"Trajet VTC direction {paiement.adresse_arrivee}")
    }]
    
    if paiement.date_retour is not None:
        date_retour_fin = paiement.date_retour+timedelta(minutes=paiement.duree_min_retour)
        ics_attachment.append({
        "filename": "reservation_retour.ics",
        "mimetype": "text/calendar",
        "content": creer_ics(paiement.date_retour, date_retour_fin, f"Trajet VTC direction {paiement.adresse_depart}") 
        })
        create_event(id_agenda_reservations,summary=f"VTC Reservation", start_dt=paiement.date_retour, end_dt=date_retour_fin, description='\n'.join(d_), location=paiement.adresse_arrivee )

    ctx = {
        "partial_refund_link": request.build_absolute_uri(
        reverse("partial_refund", args=[paiement.checkout_reference, checkout_id])
    ),
        "full_refund_link": request.build_absolute_uri(
        reverse("full_refund", args=[paiement.checkout_reference, checkout_id])
    ),
    }

    print(f"""
            partial_refund_link : {ctx['partial_refund_link']}
            full_refund_link : {ctx['full_refund_link']}
            """)

    send_email_template(
        emails=[context_client["email_client"]],
        subject="[VTC Meslé] Reservation confirmée",
        template_name="template_mail_client.html",
        context=context_client | ctx,
        attachments=ics_attachment
    )


    send_email_template(
        emails=[config.contact_email],
        subject="[VTC] Reservation confirmée",
        template_name="template_mail_owner.html",
        context={"checkout_id": checkout_id,
                    "status" : status,
                    "request" : request,
                    "data" : data
                    }
        )
    
    make_pdf(f"bon_de_reservation_{paiement.checkout_reference}.pdf","template_bon_reservation.html", context_client,"reservations/output/bons_de_reservations","reservations/static/css/style_bon.css")
    
    return HttpResponse("OK", status=200)

def welcome(request):
    context = context_init.copy()

    return render(request, 'welcome.html', context)

def download_pdf_reservation(request, client_ref):
    pdf_path = os.path.join(settings.MEDIA_ROOT, "reservations/output/bons_de_reservations", f"bon_de_reservation_{client_ref}.pdf")

    if not os.path.exists(pdf_path):
        raise Http404("PDF non trouvé")

    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

def full_refund(request, client_ref):
    trajet = Trajet.objects.get(checkout_reference=client_ref)
    transaction_id = get_transaction_id(trajet.checkout_id, sumup_api_key)
    full_refund_sumup(sumup_api_key, transaction_id)
    return HttpResponse("Trajet remboursé totalement")

def partial_refund(request, client_ref):
    trajet = Trajet.objects.get(checkout_reference=client_ref)
    transaction_id = get_transaction_id(trajet.checkout_id, sumup_api_key)
    partial_refund_sumup(sumup_api_key, transaction_id, trajet.price_euros)
    return HttpResponse("Trajet remboursé partiellement")

def facture_generation(request, client_ref):
    context = context_init.copy()
    context['form'] = AdressClientForm()
    context['client_ref'] = client_ref

    if request.method == "POST":
        form = AdressClientForm(request.POST)
        if form.is_valid(): 
            current_trajet = Trajet.objects.get(checkout_reference=client_ref)
            client = ContactClient.objects.filter(telephone_client=current_trajet.telephone_client).last()
            adress = form.cleaned_data["client_adress"]
            client.client_adress = adress
            client.save()
            context['form'] = form
            context['success_message'] = "Adresse enregistrée avec succès, ci-joint la facture correspondante."
            context_facture = get_facture_context(client_ref)
            make_pdf(f"facture_n{client_ref}.pdf","template_facture.html", context_facture,"reservations/output/factures","reservations/static/css/style_facture.css")

    return render(request, 'facture_generation.html', context)


def download_pdf_facture(request, client_ref):
    pdf_path = os.path.join(settings.MEDIA_ROOT, "reservations/output/factures", f"facture_n{client_ref}.pdf")

    if not os.path.exists(pdf_path):
        raise Http404("PDF non trouvé")

    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

def temp_trigger_webhook(request, client_ref):
    checkout_id = fct_test()
    return redirect('paiement_resultat', client_ref=client_ref)