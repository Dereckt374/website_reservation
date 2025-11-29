from django import forms
from django.utils import timezone
from .models import Trajet, ContactClient
from datetime import timedelta


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
            'date_aller': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'date_retour': forms.DateTimeInput(attrs={'type': 'datetime-local'}),                    
        }
    
    def clean(self):
        cleaned_data = super().clean()
        date_aller = cleaned_data.get("date_aller")
        date_retour = cleaned_data.get("date_retour")

        now = timezone.now()

        min_allowed = now + timedelta(minutes=5)
        if date_aller:
            if date_aller < min_allowed:
                # cleaned_data["date_aller"] = min_allowed
                self.add_error("date_aller", 
                            "L'heure de départ doit être dans le futur (minimum 5 minutes à partir de maintenant).")

        # --- 2) Validation date_retour > date_aller
        # Re-récupérer date_aller au cas où elle a été modifiée ci-dessus
        corrected_date_aller = cleaned_data.get("date_aller")

        if corrected_date_aller and date_retour:
            if date_retour <= corrected_date_aller:
                self.add_error("date_retour", 
                            "La date de retour doit être postérieure à la date d'aller.")
        return cleaned_data


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