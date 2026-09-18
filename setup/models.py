from django.db import models

class ComunicadoInterno(models.Model):
    TIPO_CHOICES = (
        ('NOVIDADE', 'Novidade / Atualização'),
        ('MANUTENCAO', 'Manutenção Programada'),
        ('ALERTA', 'Aviso Importante'),
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='NOVIDADE')
    titulo = models.CharField(max_length=150)
    texto = models.TextField()
    ativo = models.BooleanField(default=True, help_text="Desmarque para esconder da tela inicial do Lógica.Desk")
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Comunicado Interno"
        verbose_name_plural = "Comunicados Internos"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo}"