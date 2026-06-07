from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import TrajetForm, ContactClientForm, AdressClientForm, ContactForm
from .models import Trajet, ContactClient
from .utils import *
from django.conf import settings
from django.http import HttpResponse, FileResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.templatetags.static import static  # utile pour générer l'URL statique côté Python
import json
from time import sleep
import os
import requests
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

site_domain = os.getenv("site_domain")
sumup_api_key = os.getenv("sumup_api_key")
merchant_code_official = os.getenv("merchant_code_official")
current_year = datetime.now().year
id_agenda_creaneaux = os.getenv("id_agenda_creaneaux")
id_agenda_reservations = os.getenv("id_agenda_reservations")

context_init = {
        "current_year": current_year,
    }

def contact(request):
    """Page de contact générale accessible depuis la landing page"""
    context = {}
    context['entreprise_name'] = config.contact_name
    context['entreprise_siret'] = config.contact_siret
    context['type_vehicule'] = config.vehicle
    context['telephone'] = config.contact_phone
    context['email'] = config.contact_email
    context['horaires_reservation'] = config.horaires if hasattr(config, 'horaires') else "Sur demande"
    
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            # Get form data
            nom = form.cleaned_data['nom']
            prenom = form.cleaned_data['prenom']
            telephone = form.cleaned_data['telephone']
            email = form.cleaned_data['email']
            message = form.cleaned_data['message']
            
            # Send email to owner
            context_owner = {
                'nom': nom,
                'prenom': prenom,
                'telephone': telephone,
                'email': email,
                'message': message,
            }
            send_email_template(
                emails=[config.contact_email],
                subject="Nouveau message de contact",
                template_name="contact_mail_owner.html",
                context=context_owner
            )
            
            # Send email to client if email provided
            if email:
                context_client = {
                    'nom': nom,
                    'prenom': prenom,
                    'telephone': telephone,
                    'email': email,
                    'message': message,
                }
                send_email_template(
                    emails=[email],
                    subject="Confirmation de votre message",
                    template_name="contact_mail_client.html",
                    context=context_client
                )
            
            messages.success(request, "Message bien envoyé, vous serez contacté d'ici peu.")
            # Reinitialize form
            form = ContactForm()
    else:
        form = ContactForm()
    
    context['form'] = form
    return render(request, "contact.html", context=context)

def landing_page(request):
    """Page d'accueil landing page avec slider"""
    images_bank_path = "images/landing_page"
    img_dir = os.path.join(settings.MEDIA_ROOT, "reservations", "static", images_bank_path)
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

    # Charger le mapping JSON généré par la sync Drive (si présent)
    json_path = os.path.join(img_dir, "slider_texts.json")
    texts_map = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, encoding="utf-8") as f:
                texts_map = json.load(f)
        except Exception:
            texts_map = {}

    image_list = [f for f in os.listdir(img_dir) if f.lower().endswith(IMAGE_EXTS)]

    slides = []
    for name in image_list:
        stem = os.path.splitext(name)[0]
        entry = texts_map.get(name) or texts_map.get(stem)

        # Compatibilité ancien format (valeur = string) et nouveau (valeur = dict)
        if isinstance(entry, dict):
            text  = entry.get("texte") or stem
            ordre = entry.get("ordre", 9999)
        elif isinstance(entry, str):
            text  = entry
            ordre = 9999
        else:
            text  = stem
            ordre = 9999

        path = static(os.path.join(images_bank_path, name))
        slides.append({"text": text, "path": path, "ordre": ordre})

    slides.sort(key=lambda s: s["ordre"])

    context = context_init.copy()
    context["slides"] = slides

    return render(request, 'landing_page_2.html', context)

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

        elif "btnConfirmer" in request.POST and form.is_valid():
            reference = ''.join(random.sample(string.ascii_uppercase * 6, 6))
            trajet = form.save(commit=False)
            trajet.checkout_reference = reference
            trajet.save()
            request.session["trajet_id"] = trajet.id
            return redirect('contact_form', client_ref=reference)
                
        else:
            messages.error(request, "Erreur dans le formulaire ❌")
    else:
        form = TrajetForm()

    context["form"] = form

    return render(request, "reservation.html", context)

def contact_form_view(request, client_ref):
    context = context_init.copy()
    context["client_ref"] = client_ref

    trajet_id = request.session.get("trajet_id")
    if not trajet_id:
        messages.error(request, "Session expirée. Veuillez recommencer votre réservation.")
        return redirect("reservation")
    try:
        current_trajet = Trajet.objects.get(id=trajet_id)
    except Trajet.DoesNotExist:
        messages.error(request, "Réservation introuvable.")
        return redirect("reservation")

    if request.method == "POST":
        form = ContactClientForm(request.POST)
        context["form"] = form
        if form.is_valid():
            telephone  = form.cleaned_data["telephone_client"]
            email_cl   = form.cleaned_data["email_client"]
            nom        = form.cleaned_data["nom_client"]
            prenom     = form.cleaned_data["prenom_client"]
            passagers  = form.cleaned_data.get("passagers", "")

            current_trajet.telephone_client = telephone
            current_trajet.save()
            form.save()

            # Calcul distance approche
            approche = calculer_approche(current_trajet.adresse_depart, current_trajet.date_aller)

            # URL de validation pour le propriétaire
            validation_url = request.build_absolute_uri(
                reverse("valider_reservation", kwargs={"token": current_trajet.token_validation})
            )

            date_aller_str  = timezone.localtime(current_trajet.date_aller).strftime("%d/%m/%Y")
            heure_aller_str = timezone.localtime(current_trajet.date_aller).strftime("%H:%M")

            email_context = {
                "reference":            current_trajet.checkout_reference,
                "nom_client":           nom,
                "prenom_client":        prenom,
                "telephone_client":     telephone,
                "email_client":         email_cl,
                "passagers":            passagers,
                "date_aller":           date_aller_str,
                "heure_aller":          heure_aller_str,
                "adresse_depart":       current_trajet.adresse_depart,
                "adresse_arrivee":      current_trajet.adresse_arrivee,
                "type_trajet":          current_trajet.type_trajet,
                "distance_km":          current_trajet.distance_km,
                "duree_min_aller":      current_trajet.duree_min_aller,
                "price_euros":          current_trajet.price_euros,
                "commentaire_client":   current_trajet.commentaire_client,
                "approche_distance_km": approche["distance_km"],
                "approche_duree_min":   approche["duree_min"],
                "adresse_reference":    config.contact_address_private,
                "validation_url":       validation_url,
            }
            if current_trajet.date_retour:
                email_context["date_retour"]      = timezone.localtime(current_trajet.date_retour).strftime("%d/%m/%Y")
                email_context["heure_retour"]     = timezone.localtime(current_trajet.date_retour).strftime("%H:%M")
                email_context["duree_min_retour"] = current_trajet.duree_min_retour

            try:
                send_email_template(
                    emails=[config.contact_email],
                    subject=f"🚗 Nouvelle demande — Réf. {current_trajet.checkout_reference}",
                    template_name="email_proprio_nouvelle_reservation.html",
                    context=email_context,
                )
            except Exception as e:
                print(f"⚠️ Erreur envoi email propriétaire : {e}")

            # Confirmation immédiate au client
            client_context = {
                "prenom_client":      prenom,
                "nom_client":         nom,
                "reference":          current_trajet.checkout_reference,
                "adresse_depart":     current_trajet.adresse_depart,
                "adresse_arrivee":    current_trajet.adresse_arrivee,
                "date_aller":         date_aller_str,
                "heure_aller":        heure_aller_str,
                "type_trajet":        current_trajet.type_trajet,
                "distance_km":        current_trajet.distance_km,
                "price_euros":        current_trajet.price_euros,
                "telephone_contact":  config.contact_phone,
                "email_contact":      config.contact_email,
                "driver":             config.driver,
                "contact_name":       config.contact_name,
                "contact_address_public": config.contact_address_public,
                "contact_siret":      config.contact_siret,
            }
            try:
                send_email_template(
                    emails=[email_cl],
                    subject=f"✅ Votre demande de trajet a bien été reçue — Réf. {current_trajet.checkout_reference}",
                    template_name="email_client_demande_recue.html",
                    context=client_context,
                )
            except Exception as e:
                print(f"⚠️ Erreur envoi email confirmation client : {e}")

            return redirect("merci")
    else:
        context["form"] = ContactClientForm()

    return render(request, "contact_reservation.html", context=context)


def valider_reservation(request, token):
    try:
        trajet = Trajet.objects.get(token_validation=token)
    except Trajet.DoesNotExist:
        return HttpResponse("Réservation introuvable ou lien invalide.", status=404)

    if trajet.statut == "confirme":
        return render(request, "validation_ok.html", {"deja_confirme": True, "trajet": trajet})

    trajet.statut = "confirme"
    trajet.save()

    client = ContactClient.objects.filter(telephone_client=trajet.telephone_client).last()

    # Création de l'événement calendrier
    date_fin = trajet.date_aller + timedelta(minutes=int(trajet.duree_min_aller or 60))
    try:
        create_event(
            id_agenda_reservations,
            trajet.date_aller,
            date_fin,
            summary=f"VTC — {client.prenom_client} {client.nom_client}",
            description=(
                f"Réf. {trajet.checkout_reference}\n"
                f"Client : {client.nom_client} {client.prenom_client}\n"
                f"Tél : {client.telephone_client} | Email : {client.email_client}\n"
                f"Trajet : {trajet.adresse_depart} → {trajet.adresse_arrivee}\n"
                f"Distance : {trajet.distance_km} km | Durée : {trajet.duree_min_aller} min\n"
                f"Prix : {trajet.price_euros} €\n"
                f"Type : {trajet.type_trajet}"
            ),
            location=trajet.adresse_depart,
        )
    except Exception as e:
        print(f"⚠️ Erreur création événement calendrier : {e}")

    # Email de confirmation au client
    date_aller_str  = timezone.localtime(trajet.date_aller).strftime("%d/%m/%Y")
    heure_aller_str = timezone.localtime(trajet.date_aller).strftime("%H:%M")
    dt_arrivee      = trajet.date_aller + timedelta(minutes=int(trajet.duree_min_aller or 0))
    heure_arrivee   = timezone.localtime(dt_arrivee).strftime("%H:%M")

    email_context = {
        "prenom_client":        client.prenom_client,
        "nom_client":           client.nom_client,
        "reference":            trajet.checkout_reference,
        "date_aller":           date_aller_str,
        "heure_aller":          heure_aller_str,
        "heure_arrivee_est":    heure_arrivee,
        "adresse_depart":       trajet.adresse_depart,
        "adresse_arrivee":      trajet.adresse_arrivee,
        "type_trajet":          trajet.type_trajet,
        "distance_km":          trajet.distance_km,
        "duree_min_aller":      trajet.duree_min_aller,
        "price_euros":          trajet.price_euros,
        "driver":               config.driver,
        "vehicle":              config.vehicle,
        "telephone_contact":    config.contact_phone,
        "email_contact":        config.contact_email,
    }
    if trajet.date_retour:
        email_context["date_retour"]  = timezone.localtime(trajet.date_retour).strftime("%d/%m/%Y")
        email_context["heure_retour"] = timezone.localtime(trajet.date_retour).strftime("%H:%M")

    try:
        send_email_template(
            emails=[client.email_client],
            subject=f"✅ Votre réservation VTC est confirmée — Réf. {trajet.checkout_reference}",
            template_name="email_client_reservation_confirmee.html",
            context=email_context,
        )
    except Exception as e:
        print(f"⚠️ Erreur envoi email client : {e}")

    return render(request, "validation_ok.html", {
        "deja_confirme": False,
        "trajet": trajet,
        "client": client,
    })


def merci(request):
    return render(request, "merci.html", context_init.copy())

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
    url = "http://127.0.0.1:8000" + reverse("webhook")
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
        "partial_refund_link": "https://{site_domain}" + reverse("partial_refund", args=[paiement.checkout_reference, checkout_id]),
        "full_refund_link": "https://{site_domain}" + reverse("full_refund", args=[paiement.checkout_reference, checkout_id]),
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
    
    # output_path = make_pdf(f"bon_de_reservation_{paiement.checkout_reference}.pdf","template_bon_reservation.html", context_client,"reservations/output/bons_de_reservations","reservations/static/css/style_bon.css")
    # upload_file_to_drive(output_path, "BonsDeCommande", inpersonated_user=config.contact_email)

    return HttpResponse("OK", status=200)

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
            # output_path = make_pdf(f"facture_{client_ref}.pdf","template_facture.html", context_facture,"reservations/output/factures","reservations/static/css/style_facture.css")
            # upload_file_to_drive(output_path, "Factures",  inpersonated_user=config.contact_email)
    return render(request, 'facture_generation.html', context)


def download_pdf_facture(request, client_ref):
    pdf_path = os.path.join(settings.MEDIA_ROOT, "reservations/output/factures", f"facture_{client_ref}.pdf")

    if not os.path.exists(pdf_path):
        raise Http404("PDF non trouvé")

    return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

def temp_trigger_webhook(request, client_ref):
    checkout_id = fct_test()
    return redirect('paiement_resultat', client_ref=client_ref)


def welcome2(request):
    images_bank_path = "images/landing_page"
    img_dir = os.path.join(settings.MEDIA_ROOT,"reservations/static", images_bank_path)

    image_list = [f for f in os.listdir(img_dir) if f.endswith((".jpg", ".png", ".jpeg"))]
    image_path_list = [static(os.path.join(images_bank_path, image)) for image in image_list]

    context = {
        "image_dict" : dict(zip([''.join(name.split('.')[:-1]) for name in image_list], image_path_list)),
    }
    return render(request, 'landing_page_2.html', context)