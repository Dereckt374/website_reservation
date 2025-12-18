from django import forms
from django.utils import timezone
from .models import Trajet, ContactClient
from datetime import timedelta
from .utils import *
from constance import config
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

adresse_base = config.contact_address
id_agenda_creaneaux = os.getenv("id_agenda_creaneaux")
id_agenda_reservations = os.getenv("id_agenda_reservations")

class TrajetForm(forms.ModelForm):
    class Meta:
        model = Trajet
        fields =[ # "__all__"
            "adresse_depart",
            "adresse_arrivee",
            "date_aller",
            "date_retour",
            "nb_passagers",
            "commentaire_client"
        ]
        widgets = {
            'date_aller': forms.DateTimeInput(attrs={'type': 'datetime-local', 'step': 60, 'class': 'datetime-input',}, format='%Y-%m-%dT%H:%M'),
            'date_retour': forms.DateTimeInput(attrs={'type': 'datetime-local', 'step': 60,'class': 'datetime-input',}, format='%Y-%m-%dT%H:%M'),                    
        }
    def add_info(self, msg):
        self.info_message = msg
    def clean(self):
        cleaned_data = super().clean()
        now = timezone.now()
        data_trajet_retour = {"duree_min" :0,"distance_km": 0, "price_euros":0}

        if cleaned_data.get("type_trajet") is None:
            cleaned_data['type_trajet'] = self._meta.model._meta.get_field("type_trajet").default

        if cleaned_data.get("date_retour") : 
            cleaned_data["type_trajet"] = "Aller-Retour"
            data_trajet_retour = evaluer_trajet(cleaned_data["adresse_arrivee"],cleaned_data["adresse_depart"],cleaned_data['date_retour'])
        data_trajet_aller = evaluer_trajet(cleaned_data["adresse_depart"],cleaned_data["adresse_arrivee"],cleaned_data['date_aller'])

        price = data_trajet_aller['price_euros'] + data_trajet_retour['price_euros']
        cleaned_data["distance_km"] = data_trajet_aller['distance_km'] 
        cleaned_data["duree_min_aller"] = data_trajet_aller['duree_min']
        cleaned_data["duree_min_retour"] = data_trajet_retour['duree_min']
        cleaned_data["price_euros"] = price

        ## --------- VERIFICATIONS ---------
        min_allowed = now + timedelta(minutes=5)
        if cleaned_data.get("date_aller"):
            if cleaned_data.get("date_aller") < min_allowed:
                # cleaned_data["date_aller"] = min_allowed
                self.add_info("ℹ️ L'heure de départ a été ajustée.")
                cleaned_data['date_aller'] = min_allowed

        if cleaned_data.get("date_aller") and cleaned_data.get("date_retour"):
            if cleaned_data.get("date_retour") <= cleaned_data.get("date_aller"):
                self.add_error("date_retour", 
                            "❌ La date de retour doit être postérieure à la date d'aller.")
                
        if cleaned_data.get("date_aller"):
            if is_slot_available(id_agenda_creaneaux,  cleaned_data['date_aller'], data_trajet_aller['duree_min']):
                self.add_error("date_aller",
                               "❌ L'horaire pour le trajet aller est en dehors des horaires de réservation.")
        if cleaned_data.get("date_aller"):
            if not is_slot_available(id_agenda_reservations,  cleaned_data['date_aller'], data_trajet_aller['duree_min']):        
                self.add_error("date_aller",
                               "❌ Une reservation est déjà effectué sur l'horaire demandé pour le trajet aller.")
        if cleaned_data.get("date_retour") :
            if is_slot_available(id_agenda_creaneaux,  cleaned_data['date_retour'], data_trajet_retour['duree_min']):
                self.add_error("date_retour",
                               "❌ L'horaire pour le trajet retour est en dehors des horaires de réservation.")
        if cleaned_data.get("date_retour") :    
            if not is_slot_available(id_agenda_reservations,  cleaned_data['date_retour'], data_trajet_retour['duree_min']):
                self.add_error("date_retour",
                               "❌ Une reservation est déjà effectué sur l'horaire demandé pour le trajet retour.")
        if cleaned_data.get("adresse_depart") and cleaned_data.get("adresse_arrivee"):
            if cleaned_data.get("adresse_depart") == cleaned_data.get("adresse_arrivee"):
                    self.add_error("adresse_arrivee",
                                "❌ L'adresse d'arrivée doit être différente de l'adresse de départ.")  
        if cleaned_data.get("duree_min_aller") :
            if cleaned_data.get("duree_min_aller") > 240:
                self.add_error("adresse_arrivee",
                               "❌ La durée du trajet aller est trop longue (plus de 4h).")

        # if cleaned_data.get("adresse_depart") : 
        #     duree_min,distance_km,_ =  evaluer_trajet(cleaned_data["adresse_depart"],adresse_base,now)
        #     if distance_km > 500:
        #         self.add_error("adresse_depart",
        #                        "❌ L'adresse de départ est trop éloigné.")
                
        # if cleaned_data.get("adresse_arrivee") : 
        #     duree_min,distance_km,_ =  evaluer_trajet(cleaned_data["adresse_arrivee"],adresse_base,now)
        #     if distance_km > 500:
        #         self.add_error("adresse_arrivee",
        #                        "❌ L'adresse d'arrivée est trop éloigné.")


        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Transfert des valeurs calculées vers l'objet
        obj.type_trajet = self.cleaned_data["type_trajet"]
        obj.distance_km = self.cleaned_data["distance_km"]
        obj.duree_min_aller    = self.cleaned_data["duree_min_aller"]
        obj.duree_min_retour    = self.cleaned_data["duree_min_retour"]
        obj.price_euros   = self.cleaned_data["price_euros"]

        if commit:
            obj.save()

        return obj

class ContactClientForm(forms.ModelForm):

    class Meta:
        model = ContactClient
        fields = [
            "nom_client",
            "prenom_client",
            "telephone_client",
            "email_client",
            "passagers",
        ]

        widgets = {
            "nom_client": forms.TextInput(attrs={"class": "form-control"}),
            "prenom_client": forms.TextInput(attrs={"class": "form-control"}),
            "telephone_client": forms.TextInput(attrs={"class": "form-control", "placeholder": "0612345678"}),
            "email_client": forms.EmailInput(attrs={"class": "form-control", "placeholder": "exemple.email@email.fr"}),
            "passagers": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Martin Dupont 06111111, Joseph Dubois 06222222"
            }),
        }
        
class AdressClientForm(forms.ModelForm):

    class Meta:
        model = ContactClient
        fields = [
            "client_adress",
        ]

        widgets = {
            "client_adress": forms.TextInput(attrs={"class": "form-control"}),
        }