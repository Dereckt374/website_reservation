# CLAUDE.md

Site de réservation VTC (**VTC MESLE Valence**) : devis automatique, demande de réservation, validation par le chauffeur, e-mails, agenda et PDF (bon de réservation, facture).

- **Production :** https://www.mesle-entreprises.fr/
- **Admin Django :** https://www.mesle-entreprises.fr/administrator-acess/ (l'orthographe `acess` est volontaire, ne pas la corriger)
- **Langue :** code, commentaires et interface en français. Public FR, soumis au RGPD et au droit français (mentions légales, CGV).

## Architecture de production

```
Client ──HTTPS──▶ Nginx ──proxy──▶ Gunicorn ──WSGI──▶ Django (site_reservation)
                   │                  ▲
                   │                  └── supervisé par systemd (service « gunicorn »)
                   ├── sert /static/ depuis staticfiles/ (Django n'intervient pas)
                   └── certificat TLS géré par Certbot (Let's Encrypt)
```

| Composant | Rôle |
|---|---|
| **Nginx** | Serveur HTTP public : terminaison TLS, reverse proxy vers Gunicorn, service des fichiers statiques. Config : `/etc/nginx/sites-available/site_reservation` |
| **Reverse proxy** | Reçoit les requêtes des clients et les relaie vers le backend interne (Gunicorn), qui n'est jamais exposé directement |
| **Gunicorn** | Serveur d'applications WSGI pré-fork : ses workers exécutent le code Django |
| **WSGI** | Interface normalisée entre le serveur HTTP et l'application Python (`site_reservation/wsgi.py`) |
| **systemd** | Gère le cycle de vie de Gunicorn : démarrage au boot, redémarrage, logs (`journalctl -u gunicorn`) |
| **Certbot** | Obtient et renouvelle automatiquement le certificat TLS Let's Encrypt |

- **VPS :** Ubuntu, projet dans `/home/ubuntu/website_reservation`, virtualenv `.venv/`
- **Base de données :** SQLite (`db.sqlite3`, non versionnée)
- **Déploiement :** `git pull` sur le VPS, puis `sudo systemctl restart gunicorn`. Seul Gunicorn redémarre, Nginx ne change pas.

## Stack applicative

- **Django** avec une seule app : `reservations/`. Projet : `site_reservation/`
- **django-constance** (backend base de données) : les paramètres métier (tarifs, majorations, chauffeur, véhicule, contact, infos légales) sont dans `CONSTANCE_CONFIG` de `settings.py` et se modifient depuis l'admin. Pour ajouter un paramètre éditable, passer par là plutôt que par une constante en dur.
- **Services externes :**
  - Google Calendar : disponibilités et création d'événements
  - Google Drive : synchronisation des images et textes du slider de la page d'accueil (`sync_slider_from_drive`)
  - Envoi d'e-mails via SMTP
  - OpenRouteService et Google Maps : géocodage et calcul de trajet
  - SumUp : paiement et remboursement. **Les routes de paiement et le webhook sont actuellement désactivés** dans `reservations/urls.py`.
- **PDF :** `make_pdf` dans `utils.py` dépend de WeasyPrint, dont l'import est actuellement commenté (dans `requirements.txt` aussi).

## Fichiers clés

| Fichier | Contenu |
|---|---|
| `site_reservation/settings.py` | Config Django, sécurité HTTPS (active si `DEBUG=False`), `CONSTANCE_CONFIG` |
| `reservations/views.py` | Vues : landing, réservation, contact, validation, PDF, remboursements |
| `reservations/utils.py` | Toute la logique métier et les intégrations (tarif, Google, mail, SumUp, PDF, Drive) |
| `reservations/models.py` | `Trajet`, `ContactClient`, `SliderSync` |
| `reservations/legal.py` + `context_processors.py` | Infos légales injectées dans tous les templates |
| `reservations/templates/` | Templates HTML (pages, e-mails, PDF) |
| `todoes.md` | Checklist avant mise en ligne (légal, sécurité, SEO) |

## Configuration et secrets

- Les variables d'environnement sont lues depuis **`.venv/.env_prod`**, chargé par `settings.py` et `utils.py`. Ce fichier n'est pas versionné.
- Variables attendues : `django_secret_key`, `DEBUG`, `django_allowed_hosts`, `site_domain`, `ORS_API_KEY`, `sumup_api_key`, `merchant_code_official`, `json_service_account_file`, `email_appli`, `mdp_appli`, `id_agenda_creaneaux`, `id_agenda_reservations`, `slider_drive_folder_id`, `slider_excel_name`, `slider_drive_user`.
- Ne jamais écrire un secret en dur dans le code ni l'exposer côté client.

## Commandes

```bash
source .venv/bin/activate
python manage.py runserver                              # serveur de dev local
python manage.py makemigrations && python manage.py migrate
python manage.py collectstatic --noinput --clear        # à refaire après chaque changement CSS/JS
```

## Points d'attention

- **Les migrations ne sont pas versionnées** (`*/migrations/*` est dans `.gitignore`) : elles sont générées sur chaque machine. Après une modification de modèle, il faut lancer `makemigrations` puis `migrate` sur le VPS.
- `STATICFILES_STORAGE = ManifestStaticFilesStorage` : un fichier statique absent du manifest provoque une erreur 500 en production. Il faut donc lancer `collectstatic` après chaque ajout ou modification de CSS, JS ou images.
- Les tests sont des notebooks Jupyter (`reservations/tests/*.ipynb`). Il n'y a pas de suite `manage.py test` réelle.
- Dans `CONSTANCE_CONFIG`, les valeurs `[À compléter …]` doivent être renseignées dans l'admin avant la mise en ligne.
