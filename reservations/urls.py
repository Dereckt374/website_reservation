from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.welcome, name='welcome'),
    path('reservation', views.index, name="reservation"),  
    path('<str:client_ref>/contact/', views.contact_form_view, name='contact'),
    path('<str:client_ref>/contact/paiement/', views.paiement, name='paiement'),
    path('<str:client_ref>/paiement/resultat/', views.paiement_resultat, name='paiement_resultat'),
    path('webhook/', views.sumup_webhook, name='webhook'),
    path("download/<str:client_ref>/", views.download_pdf_reservation, name="download_pdf_reservation"),
    path("<str:client_ref>/<str:checkout_id>/fr/", views.full_refund, name="full_refund"),
    path("<str:client_ref>/<str:checkout_id>/pr/", views.partial_refund, name="partial_refund"),
    path("<str:client_ref>/facture_generation/", views.facture_generation, name="facture_generation"),
    path("download2/<str:client_ref>/", views.download_pdf_facture, name="download_pdf_facture"),
    path("<str:client_ref>/temp", views.temp_trigger_webhook, name="temp_trigger_webhook"),
]
