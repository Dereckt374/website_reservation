from django import forms
from .models import Trajet, ContactClient


from django import forms
from .models import Trajet

class TrajetForm(forms.ModelForm):
    class Meta:
        model = Trajet
        fields =[ # "__all__"
            "adresse_depart",
            "adresse_arrivee",
            "date_aller", 
            "nb_passagers",
            "commentaire_client"
        ]
        widgets = {
            'date_aller': forms.DateTimeInput(attrs={'type': 'datetime-local'}),          
        }

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
            "telephone_client": forms.TextInput(attrs={"class": "form-control"}),
            "email_client": forms.EmailInput(attrs={"class": "form-control"}),
            "passagers": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Exemple : Dupont 06111111, Martin 06222222"
            }),
        }