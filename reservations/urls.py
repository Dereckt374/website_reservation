from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.index, name="reservation"),  
    path('welcome/', views.welcome, name='welcome'),
    path('<str:client_ref>/contact/', views.contact_form_view, name='contact'),
    path('<str:client_ref>/contact/paiement/', views.paiement, name='paiement'),
    path('<str:client_ref>/paiement/resultat/', views.paiement_resultat, name='resultat_paiement'),
    path('webhook/', views.sumup_webhook, name='webhook'),
    path("download/<str:client_ref>/", views.download_pdf, name="download_pdf"),
    path("<int:client_ref>/<int:checkout_id>/fr/", views.full_refund, name="full_refund"),
    path("<int:client_ref>/<int:checkout_id>/pr/", views.partial_refund, name="partial_refund"),
    ]
