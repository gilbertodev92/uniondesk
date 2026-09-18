from django.contrib import admin
from .models import (
    Carteira, Transacao, ContadorAcaoMensal,
    MoldeMissao, MissaoAtiva, ProgressoMissao,
    PasseColetivo, MarcoPasse,
    ItemColecionavel, PecaRoleta, GiroRoletaLog,
    PecaInventario, ItemInventario,
    ItemLojaOficial, ResgateLojaOficial,
    AnuncioMercado,
)


@admin.register(Carteira)
class CarteiraAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nivel_atual', 'saldo_moedas', 'xp_total', 'po_magico', 'ofensiva_diaria', 'exibir_patente')
    search_fields = ('usuario__username', 'usuario__first_name')
    list_filter = ('nivel_atual',)
    readonly_fields = ('exibir_patente',)

    def exibir_patente(self, obj):
        return obj.get_patente_display()
    exibir_patente.short_description = 'Patente'


@admin.register(Transacao)
class TransacaoAdmin(admin.ModelAdmin):
    list_display = ('carteira', 'tipo', 'valor_moedas', 'valor_xp', 'data', 'descricao')
    list_filter = ('tipo', 'data')
    search_fields = ('carteira__usuario__username', 'descricao')
    date_hierarchy = 'data'


@admin.register(ContadorAcaoMensal)
class ContadorAcaoMensalAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'acao', 'ano_mes', 'quantidade')
    list_filter = ('ano_mes', 'acao')
    search_fields = ('usuario__username', 'acao')


# ── MISSÕES ──
@admin.register(MoldeMissao)
class MoldeMissaoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'gatilho', 'meta_min', 'meta_max', 'recompensa_lc', 'recompensa_xp', 'peso_sorteio', 'ativa')
    list_filter = ('tipo', 'gatilho', 'ativa')
    search_fields = ('titulo',)
    list_editable = ('ativa',)


@admin.register(MissaoAtiva)
class MissaoAtivaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'gatilho', 'meta_quantidade', 'recompensa_lc', 'periodo_inicio', 'periodo_fim')
    list_filter = ('tipo', 'periodo_inicio')
    search_fields = ('titulo',)
    date_hierarchy = 'periodo_inicio'


@admin.register(ProgressoMissao)
class ProgressoMissaoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'missao', 'progresso_atual', 'concluida', 'recompensa_resgatada', 'data_conclusao')
    list_filter = ('concluida', 'recompensa_resgatada')
    search_fields = ('usuario__username', 'missao__titulo')


# ── PASSE COLETIVO ──
class MarcoPasseInline(admin.TabularInline):
    model = MarcoPasse
    extra = 1
    ordering = ('ordem',)


@admin.register(PasseColetivo)
class PasseColetivoAdmin(admin.ModelAdmin):
    list_display = ('ano_mes', 'titulo', 'pontos_atuais', 'porcentagem', 'ativo')
    list_filter = ('ativo',)
    inlines = [MarcoPasseInline]


@admin.register(MarcoPasse)
class MarcoPasseAdmin(admin.ModelAdmin):
    list_display = ('passe', 'ordem', 'pontos_necessarios', 'recompensa_titulo', 'atingido')
    list_filter = ('atingido', 'passe')
    ordering = ('passe', 'ordem')


# ── ROLETA / ITENS ──
class PecaRoletaInline(admin.TabularInline):
    model = PecaRoleta
    extra = 0


@admin.register(ItemColecionavel)
class ItemColecionavelAdmin(admin.ModelAdmin):
    list_display = ('nome', 'raridade', 'total_pecas', 'po_ao_desencantar', 'po_para_craftar', 'efeito', 'ativo')
    list_filter = ('raridade', 'efeito', 'ativo')
    search_fields = ('nome',)
    inlines = [PecaRoletaInline]


@admin.register(PecaRoleta)
class PecaRoletaAdmin(admin.ModelAdmin):
    list_display = ('item', 'numero_peca', 'peso_sorteio', 'ativo')
    list_filter = ('ativo', 'item')


@admin.register(GiroRoletaLog)
class GiroRoletaLogAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'peca', 'data_giro')
    list_filter = ('data_giro',)
    search_fields = ('usuario__username',)
    date_hierarchy = 'data_giro'


# ── INVENTÁRIO ──
@admin.register(PecaInventario)
class PecaInventarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'item', 'numero_peca', 'origem', 'data')
    list_filter = ('origem', 'item')
    search_fields = ('usuario__username',)


@admin.register(ItemInventario)
class ItemInventarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nome_snapshot', 'status', 'data_obtencao')
    list_filter = ('status',)
    search_fields = ('usuario__username', 'nome_snapshot')


# ── LOJA OFICIAL ──
@admin.register(ItemLojaOficial)
class ItemLojaOficialAdmin(admin.ModelAdmin):
    list_display = ('nome', 'preco_lc', 'estoque', 'ativo')
    list_filter = ('ativo',)
    search_fields = ('nome',)
    list_editable = ('preco_lc', 'ativo')


@admin.register(ResgateLojaOficial)
class ResgateLojaOficialAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'item', 'custo_pago', 'status', 'data_resgate')
    list_filter = ('status', 'data_resgate')
    search_fields = ('usuario__username', 'item__nome')
    list_editable = ('status',)


# ── MERCADO CLANDESTINO ──
@admin.register(AnuncioMercado)
class AnuncioMercadoAdmin(admin.ModelAdmin):
    list_display = ('vendedor', 'tipo_conteudo', 'preco_lc', 'status', 'comprador', 'data_criacao')
    list_filter = ('status', 'tipo_conteudo')
    search_fields = ('vendedor__username', 'comprador__username')
    date_hierarchy = 'data_criacao'