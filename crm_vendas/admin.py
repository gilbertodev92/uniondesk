from django.contrib import admin
from .models import (
    Lead, MotivoPerda, MotivoExcecaoSLA, 
    HistoricoMovimentacao, AnotacaoLead, ArquivoProposta,
    Segmento, ItemProposta, VendaPessoal, MetaUsuario
)

# ==========================================
# CADASTROS AUXILIARES E METAS
# ==========================================

@admin.register(Segmento)
class SegmentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)

@admin.register(MotivoPerda)
class MotivoPerdaAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)

@admin.register(MotivoExcecaoSLA)
class MotivoExcecaoSLAAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)

@admin.register(VendaPessoal)
class VendaPessoalAdmin(admin.ModelAdmin):
    list_display = ('vendedor', 'tipo', 'valor', 'data_venda', 'descricao')
    list_filter = ('vendedor', 'tipo', 'data_venda')
    search_fields = ('descricao', 'vendedor__username', 'vendedor__first_name')

@admin.register(MetaUsuario)
class MetaUsuarioAdmin(admin.ModelAdmin):
    list_display = ('vendedor', 'mes', 'ano', 'valor_meta')
    list_filter = ('vendedor', 'mes', 'ano')

# ==========================================
# INLINES (LISTAS DENTRO DO LEAD)
# ==========================================

class HistoricoMovimentacaoInline(admin.TabularInline):
    model = HistoricoMovimentacao
    extra = 0
    readonly_fields = ('data_hora', 'vendedor', 'acao', 'detalhes')
    can_delete = False

class AnotacaoLeadInline(admin.TabularInline):
    model = AnotacaoLead
    extra = 0
    readonly_fields = ('data_criacao',)

class ArquivoPropostaInline(admin.TabularInline):
    model = ArquivoProposta
    extra = 0
    readonly_fields = ('data_upload',)

class ItemPropostaInline(admin.TabularInline):
    model = ItemProposta
    extra = 0

# ==========================================
# ADMIN PRINCIPAL DO LEAD
# ==========================================

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'nome_empresa', 'cnpj', 'etapa', 
        'vendedor_responsavel', 'status_sla', 'data_criacao'
    )
    list_filter = ('etapa', 'status_sla', 'urgencia', 'origem', 'vendedor_responsavel', 'ativo')
    search_fields = ('nome_empresa', 'nome_contato', 'cnpj', 'telefone', 'cidade')
    readonly_fields = ('id', 'data_criacao', 'ultima_atualizacao')
    
    fieldsets = (
        ('Identificação Básica', {
            'fields': ('ativo', 'cnpj', 'nome_empresa', 'nome_contato', 'telefone', 'cidade', 'segmento', 'origem', 'cliente_existente')
        }),
        ('Roteamento e Status', {
            'fields': (
                'etapa', 'status_sla',
                'vendedor_responsavel', 
                'vendedor_prospeccao', 'data_prospeccao'
            )
        }),
        ('Qualificação e Dores', {
            'fields': ('observacao_rapida', 'dor_principal', 'necessidade_desejo', 'urgencia')
        }),
        ('Proposta e Financeiro', {
            'fields': (
                'valor_equipamentos', 'valor_mensalidade', 'valor_servicos',
                'forma_pagamento', 'prazo_pagamento'
            )
        }),
        ('Reciclagem (Apenas se Perdido)', {
            'fields': ('resgatar_reciclagem', 'data_prevista_reciclagem')
        }),
        ('Controle de SLA (Exceção)', {
            'fields': ('data_limite_proximo_contato', 'motivo_excecao', 'justificativa_excecao', 'data_limite_sla', 'motivo_extensao_sla')
        }),
        ('Encerramento', {
            'fields': ('motivo_perda', 'detalhe_perda', 'data_fechamento')
        }),
        ('Sistema', {
            'fields': ('id', 'data_criacao', 'ultima_atualizacao', 'data_entrada_etapa'),
            'classes': ('collapse',)
        }),
    )
    
    inlines = [ItemPropostaInline, HistoricoMovimentacaoInline, AnotacaoLeadInline, ArquivoPropostaInline]