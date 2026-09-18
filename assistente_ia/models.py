from django.conf import settings
from django.db import models


class UsoAssistenteIA(models.Model):
    """Registra cada pergunta feita ao assistente flutuante.

    Serve tanto de log quanto de base para o relatório de 'quem mais usa'.
    """

    analista = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="usos_assistente_ia",
    )
    pergunta = models.TextField()
    resposta = models.TextField(blank=True)
    pagina = models.CharField(
        max_length=255, blank=True,
        help_text="URL ou nome da tela de onde a pergunta foi feita",
    )
    session_id = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="ID da ChatSession do whatsapp_bot, quando a pergunta foi feita dentro de um atendimento",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Uso do Assistente IA"
        verbose_name_plural = "Usos do Assistente IA"
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["analista", "criado_em"]),
        ]

    def __str__(self):
        return f"{self.analista} - {self.criado_em:%d/%m/%Y %H:%M}"
