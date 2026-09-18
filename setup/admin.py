from django.contrib import admin
from .models import ComunicadoInterno

@admin.register(ComunicadoInterno)
class ComunicadoInternoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'ativo', 'data_criacao')
    list_filter = ('tipo', 'ativo')
    search_fields = ('titulo', 'texto')