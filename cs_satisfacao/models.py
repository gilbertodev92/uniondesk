from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

# ==============================================================================
# MODELO: EVENTO DE CUSTOMER SUCCESS (MESA DE TRABALHO)
# ==============================================================================
class EventoCS(models.Model):

    class TipoContato(models.TextChoices):
        ONBOARDING = "ONBOARDING", "Pós-Implantação (Onboarding)"
        FOLLOWUP = "FOLLOWUP", "Acompanhamento de Rotina"
        TREINAMENTO = "TREINAMENTO", "Treinamento Técnico"
        RENOVACAO = "RENOVACAO", "Renovação de Contrato"
        ALERTA = "ALERTA", "Alerta de Risco / Insatisfação"
        RETENCAO = "RETENCAO", "Ação de Retenção / Negociação"
        OPORTUNIDADE = "OPORTUNIDADE", "Oportunidade de Venda (Upsell)"

    class MotivoRisco(models.TextChoices):
        NENHUM = "NENHUM", "Nenhum / Não se aplica"
        ATENDIMENTO = "ATENDIMENTO", "Reclamação do Atendimento/Comercial"
        FUNCIONALIDADE = "FUNCIONALIDADE", "Falta de Funcionalidade"
        BUGS = "BUGS", "Bugs ou Problemas não resolvidos"
        CONCORRENCIA = "CONCORRENCIA", "Ameaça da Concorrência (Preço/Sistema)"
        FINANCEIRO = "FINANCEIRO", "Dificuldade Financeira do Cliente"

    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Pendente"
        REALIZADO = "REALIZADO", "Realizado"
        CANCELADO = "CANCELADO", "Cancelado"

    origem_atendimento = models.ForeignKey(
        'atendimentos_chamados.Atendimento', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Chamado que originou este alerta de CS"
    )

    cliente = models.ForeignKey(
        "clientes_sistemas.Cliente",
        on_delete=models.CASCADE,
        related_name="eventos_cs"
    )

    responsavel = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    tipo_contato = models.CharField(
        max_length=20,
        choices=TipoContato.choices,
        default=TipoContato.FOLLOWUP
    )

    # NOVO: Para categorizar exatamente a dor que você mapeou
    motivo_risco = models.CharField(
        max_length=20,
        choices=MotivoRisco.choices,
        default=MotivoRisco.NENHUM
    )

    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDENTE
    )

    gera_oportunidade = models.BooleanField(default=False)

    data_prevista = models.DateField(default=timezone.now)
    data_realizada = models.DateField(null=True, blank=True)
    
    observacoes = models.TextField(blank=True, null=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # 1. Se marcou como realizado, crava a data
        if self.status == self.Status.REALIZADO and not self.data_realizada:
            self.data_realizada = timezone.now().date()

        # 2. Salva o evento no banco de dados
        super().save(*args, **kwargs)

        # 3. O GATILHO DE INTELIGÊNCIA: 
        # Ao salvar um evento de CS, força o cliente a recalcular a própria saúde
        if hasattr(self, 'cliente') and self.cliente:
            self.cliente.calcular_health_score()

    def __str__(self):
        return f"{self.cliente.razao_social} - {self.get_tipo_contato_display()}"


# ==============================================================================
# MODELO: REGISTRO DE CANCELAMENTO (CHURN)
# ==============================================================================
class CancelamentoCliente(models.Model):
    cliente = models.ForeignKey(
        "clientes_sistemas.Cliente",
        on_delete=models.CASCADE,
        related_name="cancelamentos"
    )
    data_cancelamento = models.DateField(
        default=timezone.now, 
        help_text="Data em que o cliente encerrou o contrato"
    )
    motivo = models.TextField(
        help_text="Motivo detalhado do cancelamento (Ex: Preço, Concorrente, Fechou a empresa, etc.)"
    )
    registrado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Primeiro salva o registro de cancelamento
        super().save(*args, **kwargs)
        
        # Depois, vai lá na tabela do Cliente e desativa ele automaticamente
        if self.cliente.ativo:
            self.cliente.ativo = False
            self.cliente.save(update_fields=['ativo'])

    def __str__(self):
        return f"Cancelamento: {self.cliente.razao_social} - {self.data_cancelamento.strftime('%d/%m/%Y')}"