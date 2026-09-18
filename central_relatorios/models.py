from django.db import models
from django.contrib.auth.models import User

class RelatorioSalvo(models.Model):
    TIPO_CHOICES = [
        ('CS', 'Customer Success'),
        ('AT', 'Atendimentos'),
        ('IMP', 'Implantações'),
        ('FIN', 'Financeiro/Saúde'),
    ]
    titulo = models.CharField(max_length=100)
    tipo = models.CharField(max_length=3, choices=TIPO_CHOICES)
    filtros_json = models.JSONField(help_text="Salva os parâmetros do filtro aplicado")
    criado_por = models.ForeignKey(User, on_delete=models.CASCADE)
    data_criacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.titulo} ({self.get_tipo_display()})"