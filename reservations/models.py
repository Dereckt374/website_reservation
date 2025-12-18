from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator, EmailValidator
from decimal import Decimal
from datetime import datetime, timedelta

def default_date():
    return (datetime.now() + timedelta(minutes=10)).replace(microsecond=0, second=0).isoformat()

class Trajet(models.Model):
    requested_at = models.DateTimeField("Heure de la Demande", default=default_date) #auto_now_add=True

    adresse_depart = models.TextField("Adresse de départ", max_length=500, default='Pôle bus, Avenue Félix Faure, Valence, France')
    adresse_arrivee = models.TextField("Adresse d'arrivée", max_length=500,  default='Valence, France')

    date_aller = models.DateTimeField("Date et heure de prise en charge", default= default_date)
    date_retour = models.DateTimeField("Date et heure de prise en charge retour", null=True, blank=True,help_text="Optionnel - Laisser vide pour un aller simple.",
)
    type_trajet = models.TextField("Type de trajet", max_length=50, default='Aller Simple')
    # Contraintes numériques
    nb_passagers = models.PositiveIntegerField(
        "Nombre de passagers",
        validators=[MinValueValidator(1), MaxValueValidator(4)],
        default = 1
    )

    # Choix limités
    VEHICULES = [
        ("berline", "Polestar 2 - 2022 - coupé 4 portes"),
    ]
    vehicule = models.CharField(
        "Type de véhicule",
        max_length=20,
        choices=VEHICULES,
        default="berline",
    )

    distance_km = models.PositiveIntegerField("Distance (km)", validators=[MinValueValidator(0), MaxValueValidator(10000)], null=True, blank=True )
    duree_min_aller = models.PositiveIntegerField("Durée Aller (minutes)", validators=[MinValueValidator(0), MaxValueValidator(2880)], null=True, blank=True)
    duree_min_retour = models.PositiveIntegerField("Durée Retour (minutes)", validators=[MinValueValidator(0), MaxValueValidator(2880)], null=True, blank=True)
    price_euros = models.DecimalField("Prix (€)",max_digits=7,decimal_places=2,validators=[MinValueValidator(Decimal("0.00")),MaxValueValidator(Decimal("10000.00"))],null=True,blank=True) 
    checkout_id = models.TextField("ID paiement sum up", max_length=1000, null=True, blank=True)
    checkout_status = models.TextField("Status paiement sum up", max_length=2000, null=True, blank=True)
    checkout_reference = models.TextField("Reference paiement sum up", max_length=1000, null=True, blank=True)

    telephone_client = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^0[1-9]\d{8}$",
                message="Le numéro doit être au format 06XXXXXXX."
            )
        ],
        null=True, blank=True
    ) 
    commentaire_client = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.adresse_depart.replace(', France','')} → {self.adresse_arrivee.replace(', France','')} ({self.distance_km}km - {self.price_euros}€ - {self.type_trajet})"
    
class ContactClient(models.Model):
    nom_client = models.CharField("Nom", max_length=100, default='Mickael')
    prenom_client = models.CharField("Prenom", max_length=100, default='Jackson')

    telephone_client = models.CharField("Telephone",
        max_length=10,
        validators=[
            RegexValidator(
                regex=r"^0[1-9]\d{8}$",
                message="Le numéro doit être au format 06XXXXXXX."
            )
        ],
        default='0601020304'
    )

    email_client = models.EmailField("Email",
                                     max_length=254,
        validators=[EmailValidator(message="Format d'email invalide.")],
        default='virgil.mesle@gmail.com'
    )

    passagers = models.TextField("Information sur les passagers",
        help_text="Format : Nom numéro de téléphone, Nom numéro de téléphone, ...",
        default='Mme Durand - 0611122233, M. Martin - 064445556',
        blank=True, null=True
    )

    client_adress = models.CharField("Adresse", max_length=500, default='', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom_client} {self.prenom_client}"