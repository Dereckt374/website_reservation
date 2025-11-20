// ===============================================
// Google Maps + Workflow de réservation manuelle
// ===============================================

let map, directionsService, directionsRenderer;

/**
 * Fonction appelée automatiquement par Google Maps
 */
function initMap() {
  directionsService = new google.maps.DirectionsService();
  directionsRenderer = new google.maps.DirectionsRenderer();

  const mapDiv = document.getElementById("map");

  // ✅ On ne crée la carte que si un élément <div id="map"> existe dans la page
  if (mapDiv) {
    map = new google.maps.Map(mapDiv, {
      zoom: 12,
      center: { lat: 44.9321, lng: 4.8911 } // Valence (FR)
    });
    directionsRenderer.setMap(map);
  }

  const inputDepart = document.getElementById("id_adresse_depart");
  const inputArrivee = document.getElementById("id_adresse_arrivee");

  // ✅ On initialise l’autocomplétion uniquement si les champs existent
  if (inputDepart) new google.maps.places.Autocomplete(inputDepart);
  if (inputArrivee) new google.maps.places.Autocomplete(inputArrivee);

  // ✅ Si on a un aperçu du trajet (par ex. après prévisualisation), on l'affiche
  afficherTrajetSiApercuPresent();
}

/**
 * Calcule et affiche le trajet sur la carte
 */
function afficherTrajetSurCarte(depart, arrivee) {
  return new Promise((resolve, reject) => {
    if (!directionsService || !directionsRenderer) {
      reject("DirectionsService non initialisé");
      return;
    }

    directionsService.route(
      {
        origin: depart,
        destination: arrivee,
        travelMode: google.maps.TravelMode.DRIVING
      },
      (response, status) => {
        if (status === "OK") {
          // ✅ Affiche uniquement si la carte existe
          if (map) directionsRenderer.setDirections(response);
          resolve();
        } else {
          reject(status);
        }
      }
    );
  });
}

/**
 * Si la div "apercu" existe, affiche automatiquement le trajet
 */
function afficherTrajetSiApercuPresent() {
  const divApercu = document.getElementById("apercu");
  if (!divApercu) return;

  const inputDepart = document.getElementById("id_adresse_depart");
  const inputArrivee = document.getElementById("id_adresse_arrivee");

  if (!inputDepart || !inputArrivee) return;

  const depart = inputDepart.value.trim();
  const arrivee = inputArrivee.value.trim();

  if (depart && arrivee) {
    afficherTrajetSurCarte(depart, arrivee)
      .catch((error) => console.error("Erreur lors de l'affichage automatique du trajet :", error));
  }
}

// ======================================================
// Gestion du bouton cochable "Aller-retour" + date_retour
// ======================================================

document.addEventListener("DOMContentLoaded", function () {
  const checkbox = document.getElementById("allerRetourCheckbox");
  const dateRow = document.getElementById("dateRetourRow");
  const dateInput = document.getElementById("id_date_retour");

  // si les éléments ne sont pas dans la page, on sort sans erreur
  if (!checkbox || !dateRow || !dateInput) return;

  function updateVisibility() {
    const checked = checkbox.checked;
    if (checked) {
      dateRow.classList.remove("hidden");
      dateRow.setAttribute("aria-hidden", "false");
      checkbox.setAttribute("aria-expanded", "true");
      dateInput.setAttribute("required", "required");
    } else {
      dateRow.classList.add("hidden");
      dateRow.setAttribute("aria-hidden", "true");
      checkbox.setAttribute("aria-expanded", "false");
      dateInput.removeAttribute("required");
      dateInput.value = "";
    }
  }

  // initialisation + écouteur d’événement
  // Si le serveur a rendu une valeur pour la date de retour, on coche la case côté client
  if (dateInput.value) {
    checkbox.checked = true;
  }
  updateVisibility();
  checkbox.addEventListener("change", updateVisibility);
});

document.getElementById("toggleForm").addEventListener("click", () => {
  const bloc = document.getElementById("formCollapse");
  bloc.classList.toggle("collapsed");
});