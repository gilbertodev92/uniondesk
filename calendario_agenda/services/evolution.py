import json
import re
import requests
from django.conf import settings

class EvolutionClient:
    def __init__(self):
        self.base = settings.EVOLUTION_API_URL.rstrip("/")
        self.key = settings.EVOLUTION_API_KEY
        self.instance = settings.EVOLUTION_INSTANCE
        self.headers = {
            "Content-Type": "application/json",
            "apikey": self.key,
        }

    @staticmethod
    def _normalize_br_number(number: str) -> str:
        """
        Normaliza para formato E.164 brasileiro: 55 + DDD + número (apenas dígitos).
        Aceita entradas com +, espaços, hífens, etc.
        Ex.: " (47) 9 9257-3078 " -> "554792573078"
        """
        digits = re.sub(r"\D", "", number or "")
        if not digits:
            return ""
        # já começa com 55?
        if digits.startswith("55"):
            return digits
        # começa com 0 (prefixos), remove
        if digits.startswith("0"):
            digits = digits.lstrip("0")
        # se tiver 10 ou 11 dígitos (DDD + número), prefixa 55
        if len(digits) in (10, 11):
            return f"55{digits}"
        # se já for 12 ou 13 (casos com 55 incluso), devolve como está
        return digits

    def send_text(self, number: str, text: str) -> dict:
        number = self._normalize_br_number(number)
        if not number:
            raise ValueError("Número inválido para WhatsApp.")
        url = f"{self.base}/message/sendText/{self.instance}"
        payload = {"number": number, "text": text}
        resp = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=30)
        resp.raise_for_status()
        return resp.json()
