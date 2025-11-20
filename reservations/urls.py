from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name="reservation"),  
    path('welcome/', views.welcome, name='welcome'),
    path('contact/', views.contact_form_view, name='contact'),
    path('contact/paiement/', views.paiement, name='paiement'),
    path('paiement/resultat/', views.paiement_resultat, name='resultat_paiement'),
    path('webhook/', views.sumup_webhook, name='webhook'),
    path('bon_de_commande/', views.bon, name='bon_de_commande'),
    ]
