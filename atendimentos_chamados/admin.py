from django.contrib import admin
from .models import Atendimento, AtendimentoHistorico, Setor


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo")


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "status", "prioridade", "tecnico_responsavel")
    list_filter = ("status", "prioridade")
    search_fields = ("titulo", "cliente__razao_social")


@admin.register(AtendimentoHistorico)
class AtendimentoHistoricoAdmin(admin.ModelAdmin):
    list_display = ("atendimento", "usuario", "data")