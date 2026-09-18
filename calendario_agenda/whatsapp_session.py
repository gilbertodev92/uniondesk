# calendario_agenda/whatsapp_session.py
from __future__ import annotations

import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class EvolutionClient:
    """
    Cliente mínimo para Evolution API.
    Espera:
      EVOLUTION_BASE_URL, EVOLUTION_INSTANCE, EVOLUTION_TOKEN em settings.
    """
    def __init__(self):
        self.base = getattr(settings, "EVOLUTION_BASE_URL", "").rstrip("/")
        self.instance = getattr(settings, "EVOLUTION_INSTANCE", "")
        self.token = getattr(settings, "EVOLUTION_TOKEN", "")

        if not self.base or not self.instance or not self.token:
            raise RuntimeError("Config Evolution incompleta (BASE/INSTANCE/TOKEN)")

        self.headers = {"apikey": self.token, "Content-Type": "application/json"}

    def send_text(self, number: str, text: str) -> bool:
        """
        Envia texto. `number` deve estar no formato 55DDDNUMERO (sem +).
        """
        url = f"{self.base}/message/sendText/{self.instance}"
        payload = {"number": number, "text": text}
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=20)
            ok = r.status_code in (200, 201)
            if not ok:
                logger.error("Evolution send_text falhou (%s): %s", r.status_code, r.text)
            return ok
        except Exception as e:
            logger.exception("Evolution send_text exception: %s", e)
            return False


class WPPConnectClient:
    """
    Cliente mínimo para WPPConnect.
    Espera:
      WPPCONNECT_BASE_URL, WPPCONNECT_SESSION, WPPCONNECT_TOKEN em settings.
    """
    def __init__(self):
        self.base = getattr(settings, "WPPCONNECT_BASE_URL", "").rstrip("/")
        self.session = getattr(settings, "WPPCONNECT_SESSION", "")
        self.token = getattr(settings, "WPPCONNECT_TOKEN", "")

        if not self.base or not self.session or not self.token:
            raise RuntimeError("Config WPPConnect incompleta (BASE/SESSION/TOKEN)")

        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def send_text(self, number: str, text: str) -> bool:
        url = f"{self.base}/api/{self.session}/send-message"
        payload = {"phone": number, "message": text}
        try:
            r = requests.post(url, json=payload, headers=self.headers, timeout=20)
            ok = r.status_code in (200, 201)
            if not ok:
                logger.error("WPPConnect send_text falhou (%s): %s", r.status_code, r.text)
            return ok
        except Exception as e:
            logger.exception("WPPConnect send_text exception: %s", e)
            return False


def get_whatsapp_client():
    provider = getattr(settings, "WHATSAPP_PROVIDER", "evolution").lower()
    if provider == "evolution":
        return EvolutionClient()
    elif provider == "wppconnect":
        return WPPConnectClient()
    raise RuntimeError(f"WHATSAPP_PROVIDER inválido: {provider}")
