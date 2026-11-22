from .legal import get_legal_context


def legal(request):
    """Rend les informations légales disponibles dans tous les templates (variable `legal`)."""
    return {"legal": get_legal_context()}
