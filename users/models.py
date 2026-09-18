from django.conf import settings
from django.db import models
from atendimentos_chamados.models import Setor


class Sistema(models.Model):
    codigo = models.AutoField(primary_key=True)
    nome = models.CharField(max_length=200)
    fabricante = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.nome} ({self.fabricante})"


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    phone_e164 = models.CharField(
        "Telefone (WhatsApp)",
        max_length=20,
        blank=True
    )

    whatsapp_opt_in = models.BooleanField(
        "Aceita lembretes via WhatsApp",
        default=True
    )

    # 🔹 NOVO CAMPO
    setor = models.ForeignKey(
        Setor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios"
    )

    def __str__(self):
        return f"Perfil de {self.user.username}"
