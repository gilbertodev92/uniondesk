# /home/logica/projetos/union/base_conhecimento/admin.py
from django.contrib import admin
from .models import Artigo

@admin.register(Artigo)
class ArtigoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "titulo", "sistema", "autor", "criado_em")
    search_fields = ("titulo", "hashtags", "codigo")
    list_filter = ("sistema", "criado_em")
