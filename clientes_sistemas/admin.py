from django.contrib import admin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    # O que aparece na lista principal
    list_display = (
        'razao_social', 
        'cnpj', 
        'faturamento_cliente', 
        'status_financeiro', 
        'nivel_risco', 
        'health_score',
        'ativo'
    )
    
    # Filtros na lateral direita
    list_filter = (
        'ativo',
        'status_financeiro',
        'faturamento_cliente',
        'nivel_risco',
        'contrato_software',
        'contrato_hardware',
    )
    
    # Campo de busca (lupa)
    search_fields = (
        'razao_social', 
        'nome_fantasia', 
        'cnpj', 
        'telefone', 
        'email', 
        'cidade'
    )
    
    # Campos que o Admin não pode editar na mão (são automáticos)
    readonly_fields = (
        'codigo',
        'health_score', 
        'nivel_risco', 
        'data_ultimo_calculo',
        'data_criacao',
        'data_atualizacao'
    )
    
    # Organização visual da tela de edição (Separando as Caixinhas)
    fieldsets = (
        ('Identificação', {
            'fields': (
                'ativo', 
                'razao_social', 
                'nome_fantasia', 
                'cnpj', 
                'inscricao_estadual', 
                'regime_tributario', 
                'data_consulta_cnpj'
            )
        }),
        ('Endereço', {
            'fields': (
                'cep', 
                'logradouro', 
                'numero', 
                'bairro', 
                'cidade', 
                'estado'
            )
        }),
        ('Contato e Responsável', {
            'fields': (
                'telefone', 
                'email', 
                'nome_responsavel', 
                'telefone_responsavel', 
                'email_responsavel'
            )
        }),
        ('Classificação e Financeiro', {
            'fields': (
                'faturamento_cliente', 
                'visibilidade_cliente', 
                'status_financeiro',
                'observacoes'
            )
        }),
        ('Serviços e Sistemas', {
            'fields': (
                'contrato_software', 
                'contrato_hardware', 
                'backup_contratado', 
                'hospedagem_datacenter',
                'sistemas',
                'serial_sistema'
            )
        }),
        ('Health Score e Sistema (Automáticos)', {
            'classes': ('collapse',), # Isso faz a aba vir fechada por padrão
            'fields': (
                'codigo',
                'health_score', 
                'nivel_risco', 
                'data_ultimo_calculo',
                'data_criacao',
                'data_atualizacao'
            )
        }),
    )