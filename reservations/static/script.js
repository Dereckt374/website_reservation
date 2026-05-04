// ===============================================
// Leaflet + Photon (autocomplete) + OSRM (carte)
// ===============================================

let map, routeLayer, departMarker, arriveeMarker;

function initMap() {
  const mapDiv = document.getElementById("map");
  if (!mapDiv) return;

  if (typeof L === "undefined") {
    console.error("Leaflet (L) n'est pas chargé — vérifiez le CDN.");
    return;
  }

  map = L.map("map").setView([44.9321, 4.8911], 12);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19
  }).addTo(map);

  // Recalcul des dimensions au cas où le conteneur n'était pas encore peint
  setTimeout(() => {
    map.invalidateSize();
    afficherTrajetSiApercuPresent();
  }, 200);
}

// ---- Géocodage Photon (même source que l'autocomplete) ----
async function geocoderAdresse(adresse) {
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(adresse)}&limit=1&lang=fr`;
  const resp = await fetch(url);
  const data = await resp.json();
  if (!data.features || !data.features.length) throw new Error(`Adresse introuvable : ${adresse}`);
  const [lon, lat] = data.features[0].geometry.coordinates;
  return { lat, lon };
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

  if (routeLayer)    { map.removeLayer(routeLayer);    routeLayer    = null; }
  if (departMarker)  { map.removeLayer(departMarker);  departMarker  = null; }
  if (arriveeMarker) { map.removeLayer(arriveeMarker); arriveeMarker = null; }

  routeLayer    = L.polyline(coords, { color: "#2563eb", weight: 5, opacity: 0.8 }).addTo(map);
  departMarker  = L.marker([coordDep.lat, coordDep.lon]).addTo(map).bindPopup("Départ").openPopup();
  arriveeMarker = L.marker([coordArr.lat, coordArr.lon]).addTo(map).bindPopup("Arrivée");

  map.fitBounds(routeLayer.getBounds(), { padding: [40, 40] });
}

function afficherTrajetSiApercuPresent() {
  const divApercu = document.getElementById("apercu");
  if (!divApercu) return;

  const depart  = divApercu.dataset.depart  || "";
  const arrivee = divApercu.dataset.arrivee || "";

  if (depart && arrivee) {
    afficherTrajetSurCarte(depart, arrivee)
      .catch(err => console.error("Erreur affichage carte :", err));
  }
}

// ---- Autocomplete Photon ----
const _photonCache = new Map();

function setupAutocomplete(input) {
  let dropdown      = null;
  let debounceTimer = null;
  let currentController = null;

  input.setAttribute("autocomplete", "off");

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < 3) { annulerRequete(); supprimerDropdown(); return; }

    if (_photonCache.has(query)) {
      afficherDropdown(_photonCache.get(query));
      return;
    }
    debounceTimer = setTimeout(() => fetchSuggestions(query), 150);
  });

  input.addEventListener("blur",   () => setTimeout(supprimerDropdown, 200));
  window.addEventListener("scroll", mettreAJourPosition, { passive: true });

  function annulerRequete() {
    if (currentController) { currentController.abort(); currentController = null; }
  }

  function fetchSuggestions(query) {
    annulerRequete();
    currentController = new AbortController();
    fetch(
      `https://photon.komoot.io/api/?q=${encodeURIComponent(query)}&limit=6&lang=fr`,
      { signal: currentController.signal }
    )
      .then(r => r.json())
      .then(data => { _photonCache.set(query, data.features); afficherDropdown(data.features); })
      .catch(err => { if (err.name !== "AbortError") console.warn("Photon:", err); });
  }

  function mettreAJourPosition() {
    if (!dropdown) return;
    const rect      = input.getBoundingClientRect();
    const dropH     = dropdown.offsetHeight;
    const spaceDown = window.innerHeight - rect.bottom;

    dropdown.style.left  = `${rect.left}px`;
    dropdown.style.width = `${rect.width}px`;
    // Bascule au-dessus si pas assez de place en dessous
    dropdown.style.top = (spaceDown < dropH && rect.top > dropH)
      ? `${rect.top - dropH}px`
      : `${rect.bottom}px`;
  }

  function afficherDropdown(features) {
    supprimerDropdown();
    if (!features || features.length === 0) return;

    dropdown = document.createElement("ul");
    dropdown.className = "autocomplete-dropdown";

    features.forEach(f => {
      const p = f.properties;
      const label = [p.name, p.street, p.housenumber, p.postcode, p.city, p.country]
        .filter(Boolean).join(", ");
      const li = document.createElement("li");
      li.textContent = label;
      li.addEventListener("mousedown", () => { input.value = label; supprimerDropdown(); });
      dropdown.appendChild(li);
    });

    // Appendé au body → aucun overflow/z-index parent ne peut le masquer
    document.body.appendChild(dropdown);
    mettreAJourPosition();  // positionnement après insertion (on connaît la hauteur)
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
