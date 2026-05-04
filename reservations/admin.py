from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html
from django.core.management import call_command

from .models import Trajet, ContactClient, SliderSync
from .utils import sync_slider_from_drive


@admin.register(Trajet)
class TrajetAdmin(admin.ModelAdmin):
    list_display = (
        "requested_at", "price_euros", "type_trajet",
        "duree_min_aller", "distance_km",
        "adresse_depart", "adresse_arrivee",
        "date_aller", "nb_passagers", "statut",
    )


@admin.register(ContactClient)
class ContactClientAdmin(admin.ModelAdmin):
    list_display = ("telephone_client", "nom_client", "prenom_client")


@admin.register(SliderSync)
class SliderSyncAdmin(admin.ModelAdmin):
    list_display   = ("synced_at", "images_count", "texts_count", "status")
    readonly_fields = ("synced_at", "images_count", "texts_count", "status")

    # Template personnalisé qui ajoute le bouton "Synchroniser"
    change_list_template = "admin/reservations/slidersync/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "sync/",
                self.admin_site.admin_view(self.run_sync_view),
                name="slidersync_run_sync",
            )
        ]
        return custom + urls

    def run_sync_view(self, request):
        """Vue appelée par le bouton 'Synchroniser depuis Drive'."""
        try:
            result = sync_slider_from_drive()

            # Collectstatic automatique pour exposer les nouvelles images
            try:
                call_command("collectstatic", "--noinput", verbosity=0)
                static_ok = True
            except Exception as e_static:
                static_ok = False
                print(f"⚠️ collectstatic échoué : {e_static}")

            status_msg = f"OK — {result['images_count']} image(s), {result['texts_count']} texte(s)"
            if not static_ok:
                status_msg += " (collectstatic échoué, relancer manuellement)"

            SliderSync.objects.create(
                images_count=result["images_count"],
                texts_count=result["texts_count"],
                status=status_msg,
            )
            self.message_user(
                request,
                format_html(
                    "✅ Sync terminée : {} image(s) importée(s), {} texte(s) chargé(s).{}",
                    result["images_count"],
                    result["texts_count"],
                    " Les fichiers statiques ont été mis à jour." if static_ok else " ⚠️ collectstatic à relancer manuellement.",
                ),
                messages.SUCCESS if static_ok else messages.WARNING,
            )
        except Exception as exc:
            SliderSync.objects.create(
                images_count=0,
                texts_count=0,
                status=f"ERREUR : {exc}",
            )
            self.message_user(
                request,
                format_html("❌ Erreur lors de la sync : {}", exc),
                messages.ERROR,
            )

        return redirect("../")   # retour vers la liste SliderSync
