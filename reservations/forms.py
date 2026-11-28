from django import forms
from django.core.validators import RegexValidator
from django.utils import timezone
from django.utils.safestring import mark_safe
from .models import Trajet, ContactClient, Forfait, default_date
from datetime import timedelta
from .utils import *
# from constance import config
from dotenv import load_dotenv
load_dotenv(dotenv_path = '.venv/.env_prod')

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

        # Champ manquant ou invalide : Django a déjà posé l'erreur sur le champ, inutile de calculer
        if not all(cleaned_data.get(c) for c in ("adresse_depart", "adresse_arrivee", "date_aller")):
            return cleaned_data

        # Calcul du trajet via OpenRouteService : une erreur d'API ne doit jamais produire une erreur 500
        try:
            if cleaned_data.get("date_retour") :
                cleaned_data["type_trajet"] = "Aller-Retour"
                data_trajet_retour = evaluer_trajet(cleaned_data["adresse_arrivee"],cleaned_data["adresse_depart"],cleaned_data['date_retour'])
            data_trajet_aller = evaluer_trajet(cleaned_data["adresse_depart"],cleaned_data["adresse_arrivee"],cleaned_data['date_aller'])
        except ValueError as e:
            # Adresse introuvable par le géocodeur
            print(f"⚠️ Géocodage : {e}")
            self.add_error(None, "❌ Une des adresses est introuvable. Vérifiez-la ou précisez la ville.")
            return cleaned_data
        except Exception as e:
            print(f"⚠️ Erreur calcul trajet (ORS) : {type(e).__name__} {e}")
            self.add_error(None, "❌ Le calcul du trajet est momentanément indisponible. "
                                 "Réessayez dans quelques instants ou contactez-nous par téléphone.")
            return cleaned_data

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
        #     duree_min,distance_km,_ =  evaluer_trajet(cleaned_data["adresse_depart"],config.contact_address,now)
        #     if distance_km > 500:
        #         self.add_error("adresse_depart",
        #                        "❌ L'adresse de départ est trop éloigné.")
                
        # if cleaned_data.get("adresse_arrivee") : 
        #     duree_min,distance_km,_ =  evaluer_trajet(cleaned_data["adresse_arrivee"],config.contact_address,now)
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
    # Acceptation expresse des CGV avant transmission de la demande (art. L221-5 et L221-14 Code de la consommation)
    accepte_cgv = forms.BooleanField(
        required=True,
        label=mark_safe(
            'J\'ai lu et j\'accepte les <a href="/cgv/" target="_blank">conditions générales de vente</a> '
        ),
        error_messages={"required": "Vous devez accepter les conditions générales de vente pour transmettre votre demande."},
    )

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


class ContactForm(forms.Form):
    nom = forms.CharField(
        label="Nom",
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Votre nom"})
    )
    prenom = forms.CharField(
        label="Prénom",
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Votre prénom"})
    )
    telephone = forms.CharField(
        label="Téléphone",
        max_length=10,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "06XXXXXXXX"}),
        validators=[
            RegexValidator(
                regex=r"^0[1-9]\d{8}$",
                message="Le numéro doit être au format 0XXXXXXXX."
            )
        ]
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "votre.email@example.com"})
    )
    message = forms.CharField(
        label="Message",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Votre message..."
        })
    )


class ForfaitChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.nom_depart} → {obj.nom_arrivee}"


class ForfaitReservationForm(forms.Form):
    """Demande de trajet au forfait : trajet prédéfini, seule l'heure de prise en charge est choisie."""
    forfait = ForfaitChoiceField(
        label="Forfait",
        queryset=Forfait.objects.filter(actif=True),
        widget=forms.RadioSelect,
        empty_label=None,
        error_messages={"required": "Choisissez un forfait.", "invalid_choice": "Ce forfait n'est plus disponible."},
    )
    date_aller = forms.DateTimeField(
        label="Date et heure de prise en charge",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "step": 60, "class": "datetime-input"}, format="%Y-%m-%dT%H:%M"),
        initial=default_date,
    )
    nb_passagers = forms.IntegerField(label="Nombre de passagers", min_value=1, max_value=4, initial=1)
    commentaire_client = forms.CharField(label="Commentaire", required=False, widget=forms.Textarea)

    def clean(self):
        cleaned_data = super().clean()
        forfait = cleaned_data.get("forfait")
        date_aller = cleaned_data.get("date_aller")
        if not forfait or not date_aller:
            return cleaned_data

        min_allowed = timezone.now() + timedelta(minutes=5)
        if date_aller < min_allowed:
            self.info_message = "ℹ️ L'heure de départ a été ajustée."
            date_aller = cleaned_data["date_aller"] = min_allowed

        duree = forfait.duree_min or 60
        if is_slot_available(id_agenda_creaneaux, date_aller, duree):
            self.add_error("date_aller", "❌ L'horaire demandé est en dehors des horaires de réservation.")
        elif not is_slot_available(id_agenda_reservations, date_aller, duree):
            self.add_error("date_aller", "❌ Une reservation est déjà effectué sur l'horaire demandé.")

        cleaned_data["prix"] = prix_forfait(forfait.tarif, date_aller)
        return cleaned_data

    def build_trajet(self):
        """Trajet (non enregistré) correspondant au forfait choisi."""
        forfait = self.cleaned_data["forfait"]
        return Trajet(
            adresse_depart=forfait.adresse_depart,
            adresse_arrivee=forfait.adresse_arrivee,
            date_aller=self.cleaned_data["date_aller"],
            type_trajet=f"Forfait : {forfait.nom_depart} → {forfait.nom_arrivee}",
            nb_passagers=self.cleaned_data["nb_passagers"],
            commentaire_client=self.cleaned_data.get("commentaire_client") or None,
            distance_km=round(forfait.distance_km) if forfait.distance_km is not None else None,
            duree_min_aller=forfait.duree_min,
            duree_min_retour=0,
            price_euros=self.cleaned_data["prix"]["prix"],
        )
