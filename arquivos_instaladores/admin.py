from django.contrib import admin
from .models import ArquivoItem


@admin.register(ArquivoItem)
class ArquivoItemAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "versao", "is_ativo", "criado_em", "criado_por")
    list_filter = ("categoria", "is_ativo", "criado_em")
    search_fields = ("titulo", "descricao", "versao")
    readonly_fields = ("tamanho_bytes", "checksum_sha256", "criado_em", "atualizado_em")
