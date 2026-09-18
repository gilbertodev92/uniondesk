from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Implantacao(models.Model):

    class Status(models.TextChoices):
        PLANEJAMENTO = "PLANEJAMENTO", "Planejamento"
        EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
        AGUARDANDO_CLIENTE = "AGUARDANDO_CLIENTE", "Aguardando cliente"
        CONCLUIDA = "CONCLUIDA", "Concluída"
        CANCELADA = "CANCELADA", "Cancelada"

    cliente = models.ForeignKey(
        "clientes_sistemas.Cliente",
        on_delete=models.CASCADE,
        related_name="implantacoes"
    )

    sistema = models.ForeignKey(
        "sistemas.Sistema",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="implantacoes"
    )

    responsavel = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="implantacoes_responsavel"
    )

    titulo = models.CharField(max_length=255)
    descricao = models.TextField(blank=True)

    status = models.CharField(
        max_length=25,
        choices=Status.choices,
        default=Status.PLANEJAMENTO
    )

    data_inicio = models.DateTimeField(default=timezone.now)
    data_prevista = models.DateTimeField(null=True, blank=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)

    gerar_cs_automatico = models.BooleanField(default=True)

    def __str__(self):
        return f"Implantação - {self.cliente}"
