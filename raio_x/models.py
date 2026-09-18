from django.db import models
from decimal import Decimal

class RaioXConfig(models.Model):
    senha_mestra = models.CharField(
        max_length=255, 
        default="@H3xt0r111", 
        help_text="Senha Mestra para liberar o acesso ao painel de Auditoria."
    )
    peso_os = models.IntegerField(
        default=35, 
        help_text="Pontos por cada O.S. concluída no Radar."
    )
    peso_implantacao = models.IntegerField(
        default=50, 
        help_text="Pontos de bônus por O.S. de implantação de cliente ou módulo."
    )
    peso_cs = models.IntegerField(
        default=17, 
        help_text="Pontos por contato/ação de Customer Success realizada."
    )
    peso_agenda = models.IntegerField(
        default=40, 
        help_text="Pontos por agendamentos e visitas externas concluídas."
    )
    peso_msg_zap = models.DecimalField(
        max_digits=4, 
        decimal_places=2, 
        default=Decimal('0.05'), 
        help_text="Pontos por cada mensagem individual enviada por técnicos no WhatsApp."
    )
    peso_avaliacao = models.IntegerField(
        default=5, 
        help_text="Pontos por avaliação positiva (4 ou 5 estrelas) recebida do cliente no WhatsApp."
    )

    class Meta:
        verbose_name = "Configuração do Raio-X"
        verbose_name_plural = "Configurações do Raio-X"

    def __str__(self):
        return "Configuração Global do Raio-X"