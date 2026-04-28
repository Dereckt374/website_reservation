// ===============================================
// Leaflet + Photon (autocomplete) + OSRM (carte)
// ===============================================

let map, routeLayer, departMarker, arriveeMarker;

function initMap() {
  const mapDiv = document.getElementById("map");
  if (!mapDiv) return;

  map = L.map("map").setView([44.9321, 4.8911], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  }).addTo(map);

  afficherTrajetSiApercuPresent();
}

// ---- Géocodage Nominatim ----
async function geocoderAdresse(adresse) {
  const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(adresse)}&format=json&limit=1&countrycodes=fr,mc,be,ch,lu`;
  const resp = await fetch(url, { headers: { "Accept-Language": "fr" } });
  const data = await resp.json();
  if (!data.length) throw new Error(`Adresse introuvable : ${adresse}`);
  return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
}

// ---- Affichage de l'itinéraire via OSRM ----
async function afficherTrajetSurCarte(depart, arrivee) {
  const [coordDep, coordArr] = await Promise.all([
    geocoderAdresse(depart),
    geocoderAdresse(arrivee)
  ]);

  const url = `https://router.project-osrm.org/route/v1/driving/${coordDep.lon},${coordDep.lat};${coordArr.lon},${coordArr.lat}?overview=full&geometries=geojson`;
  const resp = await fetch(url);
  const data = await resp.json();

  if (data.code !== "Ok") throw new Error("Calcul itinéraire OSRM échoué");

  const coords = data.routes[0].geometry.coordinates.map(c => [c[1], c[0]]);

  if (routeLayer)   { map.removeLayer(routeLayer);   routeLayer   = null; }
  if (departMarker) { map.removeLayer(departMarker); departMarker = null; }
  if (arriveeMarker){ map.removeLayer(arriveeMarker);arriveeMarker= null; }

  routeLayer    = L.polyline(coords, { color: "#2563eb", weight: 5, opacity: 0.8 }).addTo(map);
  departMarker  = L.marker([coordDep.lat, coordDep.lon]).addTo(map).bindPopup("Départ").openPopup();
  arriveeMarker = L.marker([coordArr.lat, coordArr.lon]).addTo(map).bindPopup("Arrivée");

  map.fitBounds(routeLayer.getBounds(), { padding: [40, 40] });
}

function afficherTrajetSiApercuPresent() {
  const divApercu = document.getElementById("apercu");
  if (!divApercu) return;

  const inputDepart  = document.getElementById("id_adresse_depart");
  const inputArrivee = document.getElementById("id_adresse_arrivee");
  if (!inputDepart || !inputArrivee) return;

  const depart  = inputDepart.value.trim();
  const arrivee = inputArrivee.value.trim();

  if (depart && arrivee) {
    afficherTrajetSurCarte(depart, arrivee)
      .catch(err => console.error("Erreur affichage carte :", err));
  }
}

// ---- Autocomplete Photon ----
function setupAutocomplete(input) {
  let dropdown = null;
  let debounceTimer = null;

  input.setAttribute("autocomplete", "off");

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < 3) { supprimerDropdown(); return; }
    debounceTimer = setTimeout(() => fetchSuggestions(query), 300);
  });

  input.addEventListener("blur", () => {
    setTimeout(supprimerDropdown, 200);
  });

  function fetchSuggestions(query) {
    fetch(`https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&limit=6&lang=fr`)
      .then(r => r.json())
      .then(data => afficherDropdown(data.features))
      .catch(() => {});
  }

  function afficherDropdown(features) {
    supprimerDropdown();
    if (!features || features.length === 0) return;

    dropdown = document.createElement("ul");
    dropdown.className = "autocomplete-dropdown";

    const rect = input.getBoundingClientRect();
    dropdown.style.top   = `${rect.bottom + window.scrollY}px`;
    dropdown.style.left  = `${rect.left  + window.scrollX}px`;
    dropdown.style.width = `${rect.width}px`;

    features.forEach(f => {
      const p = f.properties;
      const label = [p.name, p.street, p.housenumber, p.postcode, p.city, p.country]
        .filter(Boolean).join(", ");
      const li = document.createElement("li");
      li.textContent = label;
      li.addEventListener("mousedown", () => {
        input.value = label;
        supprimerDropdown();
      });
      dropdown.appendChild(li);
    });

    document.body.appendChild(dropdown);
  }

  function supprimerDropdown() {
    if (dropdown) { dropdown.remove(); dropdown = null; }
  }
}

// ---- Init au chargement ----
document.addEventListener("DOMContentLoaded", () => {
  const inputDepart  = document.getElementById("id_adresse_depart");
  const inputArrivee = document.getElementById("id_adresse_arrivee");

  if (inputDepart)  setupAutocomplete(inputDepart);
  if (inputArrivee) setupAutocomplete(inputArrivee);

  const toggleBtn = document.getElementById("toggleForm");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      document.getElementById("formCollapse").classList.toggle("collapsed");
    });
  }

  initMap();
});
