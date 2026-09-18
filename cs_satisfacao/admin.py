from django.contrib import admin
from django.utils.html import format_html
from .models import EventoCS, CancelamentoCliente

@admin.register(EventoCS)
class EventoCSAdmin(admin.ModelAdmin):
    # ==========================================
    # 1. O QUE APARECE NA LISTA PRINCIPAL
    # ==========================================
    list_display = (
        "cliente",
        "tipo_contato",
        "motivo_risco",
        "status_badge", # Usa a função colorida que criamos abaixo
        "data_prevista",
        "responsavel",
        "gera_oportunidade",
    )

    # ==========================================
    # 2. FILTROS LATERAIS E BUSCA
    # ==========================================
    list_filter = (
        "status",
        "tipo_contato",
        "motivo_risco",
        "gera_oportunidade",
        "data_prevista",
        "responsavel",
    )
    search_fields = ("cliente__razao_social", "cliente__cnpj", "observacoes")
    
    # Cria uma linha do tempo clicável no topo da página
    date_hierarchy = "data_prevista"

    # ==========================================
    # 3. PERFORMANCE (Evita travar com muitos dados)
    # ==========================================
    # Usa uma lupa de busca em vez de carregar um dropdown com 5.000 clientes/usuários
    raw_id_fields = ("cliente", "responsavel", "origem_atendimento")

    # ==========================================
    # 4. ORGANIZAÇÃO DO FORMULÁRIO INTERNO
    # ==========================================
    fieldsets = (
        ("Informações Principais", {
            "fields": ("cliente", "responsavel", "origem_atendimento")
        }),
        ("Estratégia e Risco", {
            "fields": ("tipo_contato", "motivo_risco", "status", "gera_oportunidade")
        }),
        ("Cronograma", {
            "fields": ("data_prevista", "data_realizada")
        }),
        ("Anotações do CS", {
            "fields": ("observacoes",)
        }),
    )

    # ==========================================
    # 5. MÉTODOS VISUAIS (BADGES)
    # ==========================================
    @admin.display(description="Status")
    def status_badge(self, obj):
        cores = {
            "PENDENTE": "#f97316",  # Laranja
            "REALIZADO": "#10b981", # Verde
            "CANCELADO": "#6b7280", # Cinza
        }
        cor = cores.get(obj.status, "#000000")
        return format_html(
            '<span style="color: white; background-color: {}; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 10px; letter-spacing: 1px;">{}</span>',
            cor,
            obj.get_status_display().upper()
        )


@admin.register(CancelamentoCliente)
class CancelamentoClienteAdmin(admin.ModelAdmin):
    list_display = (
        'cliente', 
        'data_cancelamento', 
        'registrado_por', 
        'criado_em'
    )
    list_filter = ('data_cancelamento', 'registrado_por')
    search_fields = ('cliente__razao_social', 'cliente__cnpj', 'motivo')
    date_hierarchy = 'data_cancelamento'

    raw_id_fields = ("cliente", "registrado_por")

    fieldsets = (
        ("Dados do Cancelamento (Churn)", {
            "fields": ("cliente", "data_cancelamento", "registrado_por")
        }),
        ("Análise e Motivo", {
            "fields": ("motivo",)
        }),
    )