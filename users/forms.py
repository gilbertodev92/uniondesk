from django import forms
from django.contrib.auth.models import User, Group
from sistemas.models import Sistema
from .models import Profile

# ------ SistemaForm (como você já usava no painel) ------
class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ['nome', 'fabricante']
        widgets = {
            'nome': forms.TextInput(attrs={
                "class": "w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            }),
            'fabricante': forms.TextInput(attrs={
                "class": "w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            }),
        }

# ------ Normalização simples para E.164 ------
def normalize_phone_to_e164(raw: str) -> str:
    """
    Normaliza telefone para algo próximo de E.164.
    Se vier só dígitos com DDD (ex: 11999998888), prefixa +55.
    Se vier com + e dígitos, mantém.
    """
    if not raw:
        return ""
    s = "".join(ch for ch in str(raw) if ch.isdigit() or ch == "+").strip()
    if not s:
        return ""
    if s.startswith("+"):
        return s
    if s.isdigit():
        return "+55" + s
    return s

# ------ ProfileForm (telefone + opt-in) ------
class ProfileForm(forms.ModelForm):
    phone_display = forms.CharField(
        label="WhatsApp (com DDD)",
        required=False,
        help_text="Ex.: 11 99999-8888 (salvamos como +5511999998888)"
    )

    class Meta:
        model = Profile
        fields = ["whatsapp_opt_in"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone_display"].initial = getattr(self.instance, "phone_e164", "")

    def clean(self):
        cleaned = super().clean()
        raw = cleaned.get("phone_display") or ""
        e164 = normalize_phone_to_e164(raw)
        if raw and (not e164.startswith("+") or len(e164) < 8):
            self.add_error("phone_display", "Telefone inválido. Informe com DDD. Ex.: 11 99999-8888")
        self.instance.phone_e164 = e164
        return cleaned
