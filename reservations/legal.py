"""Informations légales de l'entreprise, centralisées pour les pages, les emails et les factures."""
from constance import config


def get_legal_context():
    return {
        "name": config.contact_name,
        "form": config.legal_form,
        "owner": config.legal_owner,
        "address": config.legal_address,
        "city": config.contact_address_public,
        "siret": config.contact_siret,
        "registration": config.legal_registration,
        "vat_mention": config.legal_vat_mention,
        "vtc_registry": config.legal_vtc_registry,
        "insurance": config.legal_insurance,
        "publication_director": config.legal_publication_director,
        "host": config.legal_host,
        "mediator": config.legal_mediator,
        "cancellation": config.legal_cancellation,
        "updated": config.legal_cgv_updated,
        "email": config.contact_email,
        "phone": config.contact_phone,
        "hourly_cost": config.hourly_cost,
        "price_per_km": config.price_per_km,
        "evening_factor": config.evening_factor,
        "night_factor": config.night_factor,
        "vehicle": config.vehicle,
    }
