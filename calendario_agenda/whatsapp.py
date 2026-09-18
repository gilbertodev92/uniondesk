# calendario_agenda/whatsapp.py
from django.conf import settings

def send_whatsapp_message(phone_e164: str, text: str) -> bool:
    """
    Gancho opcional para WhatsApp.
    Retorna False por padrão (sem integrar a nada). Se configurar sua API,
    implemente aqui e retorne True em caso de sucesso.
    """
    provider = getattr(settings, "WHATSAPP_PROVIDER", "").lower()
    if not provider:
        return False

    # Exemplo (pseudo):
    # if provider == "meta":
    #     import requests
    #     token = settings.WHATSAPP_META_TOKEN
    #     phone_id = settings.WHATSAPP_META_PHONE_ID
    #     resp = requests.post("https://graph.facebook.com/v20.0/{phone_id}/messages", ...)
    #     return resp.status_code == 200

    return False
