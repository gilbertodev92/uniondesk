# controle_horas/admin.py
from django.contrib import admin
from .models import ConfigHoras, Apontamento, FechamentoMensal


@admin.register(ConfigHoras)
class ConfigHorasAdmin(admin.ModelAdmin):
    # Coloquei um campo "id" primeiro para ser o link da linha
    list_display = ("id", "ativo", "horas_dia", "pausa_almoco_min",
                    "considerar_sabado", "considerar_domingo")
    list_display_links = ("id",)              # link da linha
    list_editable = ("ativo",)                # agora pode editar na lista
    list_filter = ("ativo", "considerar_sabado", "considerar_domingo")
    search_fields = ()


@admin.register(Apontamento)
class ApontamentoAdmin(admin.ModelAdmin):
    list_display = ("data", "usuario", "tipo", "status", "horas_total", "horas_extra")
    list_filter = ("status", "tipo", "data")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "descricao")
    autocomplete_fields = ("usuario",)
    date_hierarchy = "data"
    ordering = ("-data",)

# Se o model tiver o campo 'sistema', acrescenta dinamicamente nas colunas/filtros
if "sistema" in [f.name for f in Apontamento._meta.get_fields()]:
    ApontamentoAdmin.list_display = ("data", "usuario", "sistema", "tipo", "status", "horas_total", "horas_extra")
    ApontamentoAdmin.list_filter = ("status", "tipo", "data", "sistema")


@admin.register(FechamentoMensal)
class FechamentoMensalAdmin(admin.ModelAdmin):
    list_display = ("usuario", "competencia", "fechado", "fechado_em")
    list_filter = ("fechado", "competencia")
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name")
    autocomplete_fields = ("usuario",)
    date_hierarchy = "competencia"
    ordering = ("-competencia", "usuario__username")
