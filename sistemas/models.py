from django.db import models

class Sistema(models.Model):
    codigo = models.AutoField(primary_key=True)  # código sequencial automático
    nome = models.CharField(max_length=100, unique=True)  # nome do sistema
    fabricante = models.CharField(max_length=100)  # fabricante do sistema

    def __str__(self):
        return f"{self.nome} ({self.fabricante})"
