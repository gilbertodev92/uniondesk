from django.contrib import admin

from .models import UsoAssistenteIA


@admin.register(UsoAssistenteIA)
class UsoAssistenteIAAdmin(admin.ModelAdmin):
    list_display = ("analista", "pagina", "session_id", "criado_em")
    list_filter = ("pagina", "criado_em")
    search_fields = ("analista__username", "pergunta", "session_id")
    readonly_fields = ("analista", "pergunta", "resposta", "pagina", "session_id", "criado_em")
