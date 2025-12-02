from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Trajet, ContactClient

@admin.register(Trajet)
class TrajetAdmin(admin.ModelAdmin):
    list_display = ("requested_at","price_euros","type_trajet","duree_min_aller","distance_km","adresse_depart", "adresse_arrivee", "date_aller", "nb_passagers")


@admin.register(ContactClient)
class TrajetAdmin(admin.ModelAdmin):
    list_display = ("telephone_client","nom_client", "prenom_client")

