from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ══════════════════════════════════════════════════════════════════
# 1. CARTEIRA — o perfil RPG do técnico
# ══════════════════════════════════════════════════════════════════
class Carteira(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name="carteira")
    saldo_moedas = models.IntegerField(default=0, help_text="Lógica Coins (LC) disponíveis")
    xp_total = models.IntegerField(default=0, help_text="XP acumulado de toda a vida")
    nivel_atual = models.IntegerField(default=1)

    po_magico = models.IntegerField(default=0, help_text="Pó Mágico — matéria-prima para craftar peças")

    ofensiva_diaria = models.IntegerField(default=0, help_text="Dias seguidos de check-in")
    maior_ofensiva = models.IntegerField(default=0, help_text="Recorde de ofensiva")
    ultimo_resgate_diario = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-xp_total",)

    def __str__(self):
        return f"{self.usuario.username} — Nv {self.nivel_atual} | {self.saldo_moedas} LC"

    @property
    def xp_piso_nivel(self):
        return 100 * ((self.nivel_atual - 1) ** 2)

    @property
    def xp_proximo_nivel(self):
        return 100 * (self.nivel_atual ** 2)

    @property
    def porcentagem_barra_xp(self):
        piso, teto = self.xp_piso_nivel, self.xp_proximo_nivel
        feito = self.xp_total - piso
        necessario = teto - piso
        if necessario <= 0:
            return 100
        return min(max(int((feito / necessario) * 100), 0), 100)

    def get_patente_display(self):
        n = self.nivel_atual
        if n <= 10: return "Novato"
        if n <= 15: return "Aprendiz"
        if n <= 20: return "Suporte Júnior"
        if n <= 30: return "Suporte Pleno"
        if n <= 40: return "Suporte Sênior"
        if n <= 50: return "Especialista"
        if n <= 65: return "Tropa de Elite"
        if n <= 80: return "Mestre"
        if n <= 95: return "Lenda"
        return "Lenda Suprema"


# ══════════════════════════════════════════════════════════════════
# 2. RENDIMENTO DECRESCENTE — o coração do balanceamento
# ══════════════════════════════════════════════════════════════════
class ContadorAcaoMensal(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contadores_acao")
    acao = models.CharField(max_length=60)
    ano_mes = models.CharField(max_length=7, help_text="Formato AAAA-MM")
    quantidade = models.IntegerField(default=0)

    class Meta:
        unique_together = ("usuario", "acao", "ano_mes")
        indexes = [models.Index(fields=["usuario", "ano_mes"])]

    def __str__(self):
        return f"{self.usuario.username} · {self.acao} · {self.ano_mes}: {self.quantidade}x"


# ══════════════════════════════════════════════════════════════════
# 3. EXTRATO
# ══════════════════════════════════════════════════════════════════
class Transacao(models.Model):
    class Tipo(models.TextChoices):
        GANHO = "GANHO", "Ganho (+)"
        GASTO = "GASTO", "Gasto (-)"

    carteira = models.ForeignKey(Carteira, on_delete=models.CASCADE, related_name="transacoes")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    valor_moedas = models.IntegerField(default=0)
    valor_xp = models.IntegerField(default=0)
    descricao = models.CharField(max_length=255)
    data = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-data",)

    def __str__(self):
        s = "+" if self.tipo == self.Tipo.GANHO else "-"
        return f"[{self.data:%d/%m}] {self.carteira.usuario.username}: {s}{self.valor_moedas} LC"


# ══════════════════════════════════════════════════════════════════
# 4. MISSÕES — moldes + instâncias geradas automaticamente
# ══════════════════════════════════════════════════════════════════
class MoldeMissao(models.Model):
    class Tipo(models.TextChoices):
        DIARIA = "DIARIA", "Diária"
        SEMANAL = "SEMANAL", "Semanal"
        MENSAL = "MENSAL", "Mensal"

    class Gatilho(models.TextChoices):
        FECHAR_CHAMADO = "fechar_chamado", "Fechar Atendimento"
        FINALIZAR_CHAT = "finalizar_chat", "Finalizar Chat (bot)"
        FINALIZAR_GRUPO = "finalizar_grupo", "Atender em Grupo"
        RESPONDER_GRUPO = "responder_grupo", "Responder em Grupo"
        REGISTRAR_CS = "registrar_contato_cs", "Registrar CS"
        FEEDBACK_5 = "feedback_5_estrelas", "Avaliação 5 estrelas"
        CADASTRAR_BASE = "cadastrar_base_conhecimento", "Criar Artigo"
        SUBIR_ARQUIVO = "subir_arquivo", "Subir Instalador"
        CRIAR_EVENTO = "criar_evento_agenda", "Agendar no Calendário"
        CADASTRAR_CLIENTE = "cadastrar_cliente", "Cadastrar Cliente"
        VINCULAR_CLIENTE = "vincular_cliente", "Vincular Cliente"

    titulo = models.CharField(max_length=100)
    descricao = models.CharField(max_length=200, blank=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    gatilho = models.CharField(max_length=50, choices=Gatilho.choices)
    meta_min = models.IntegerField(default=1)
    meta_max = models.IntegerField(default=1)
    recompensa_lc = models.IntegerField(default=0)
    recompensa_xp = models.IntegerField(default=0)
    peso_sorteio = models.IntegerField(default=1, help_text="Chance relativa de ser sorteada")
    ativa = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.titulo}"


class MissaoAtiva(models.Model):
    molde = models.ForeignKey(MoldeMissao, on_delete=models.CASCADE, related_name="instancias")
    tipo = models.CharField(max_length=10, choices=MoldeMissao.Tipo.choices)
    gatilho = models.CharField(max_length=50)
    titulo = models.CharField(max_length=100)
    descricao = models.CharField(max_length=200, blank=True)
    meta_quantidade = models.IntegerField(default=1)
    recompensa_lc = models.IntegerField(default=0)
    recompensa_xp = models.IntegerField(default=0)
    periodo_inicio = models.DateField()
    periodo_fim = models.DateField()

    class Meta:
        indexes = [models.Index(fields=["tipo", "periodo_inicio", "periodo_fim"])]

    def __str__(self):
        return f"[{self.tipo}] {self.titulo} ({self.periodo_inicio}→{self.periodo_fim})"


class ProgressoMissao(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="progressos")
    missao = models.ForeignKey(MissaoAtiva, on_delete=models.CASCADE, related_name="progressos")
    progresso_atual = models.IntegerField(default=0)
    concluida = models.BooleanField(default=False)
    recompensa_resgatada = models.BooleanField(default=False)
    data_conclusao = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("usuario", "missao")

    def __str__(self):
        return f"{self.usuario.username} · {self.missao.titulo}: {self.progresso_atual}/{self.missao.meta_quantidade}"


# ══════════════════════════════════════════════════════════════════
# 5. PASSE COLETIVO — a barra da equipe (mensal)
# ══════════════════════════════════════════════════════════════════
class PasseColetivo(models.Model):
    ano_mes = models.CharField(max_length=7, unique=True, help_text="AAAA-MM")
    titulo = models.CharField(max_length=100, default="Meta da Equipe")
    pontos_atuais = models.IntegerField(default=0)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"Passe {self.ano_mes} — {self.pontos_atuais} pts"

    @property
    def pontos_maximos(self):
        ultimo = self.marcos.order_by("-pontos_necessarios").first()
        return ultimo.pontos_necessarios if ultimo else 0

    @property
    def porcentagem(self):
        teto = self.pontos_maximos
        if teto <= 0:
            return 0
        return min(int((self.pontos_atuais / teto) * 100), 100)


class MarcoPasse(models.Model):
    passe = models.ForeignKey(PasseColetivo, on_delete=models.CASCADE, related_name="marcos")
    ordem = models.IntegerField(default=1)
    pontos_necessarios = models.IntegerField()
    recompensa_titulo = models.CharField(max_length=120, help_text="Ex: Cuca para a equipe")
    recompensa_descricao = models.CharField(max_length=200, blank=True)
    icone = models.CharField(max_length=40, default="fa-gift")
    atingido = models.BooleanField(default=False)
    data_atingido = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("ordem",)

    def __str__(self):
        return f"{self.passe.ano_mes} · Marco {self.ordem}: {self.recompensa_titulo}"


# ══════════════════════════════════════════════════════════════════
# 6. ROLETA COM PEÇAS DE QUEBRA-CABEÇA
# ══════════════════════════════════════════════════════════════════
class ItemColecionavel(models.Model):
    class Raridade(models.TextChoices):
        COMUM = "COMUM", "Comum"
        RARO = "RARO", "Raro"
        EPICO = "EPICO", "Épico"
        LENDARIO = "LENDARIO", "Lendário"

    nome = models.CharField(max_length=100)
    descricao = models.CharField(max_length=200, blank=True)
    icone = models.CharField(max_length=40, default="fa-puzzle-piece")
    raridade = models.CharField(max_length=10, choices=Raridade.choices, default=Raridade.COMUM)
    total_pecas = models.IntegerField(default=4, help_text="Quantas peças formam o item")

    # Economia do pó (calibrada por raridade; craft ≈ 3.5x o desencante)
    po_ao_desencantar = models.IntegerField(default=8, help_text="Pó ganho ao desencantar 1 peça deste item")
    po_para_craftar = models.IntegerField(default=28, help_text="Pó gasto para craftar 1 peça deste item")

    # o que acontece quando o item completo é resgatado (efeito real)
    class Efeito(models.TextChoices):
        HOME_OFFICE = "HOME_OFFICE", "Home Office (1 dia remoto)"
        DAY_OFF = "DAY_OFF", "Day Off (folga)"
        PACK_XP = "PACK_XP", "Pack de XP (turbo no perfil)"
        FISICO = "FISICO", "Item físico (entregue pela gestão)"
    efeito = models.CharField(max_length=15, choices=Efeito.choices, default=Efeito.FISICO)
    valor_efeito = models.IntegerField(default=0, help_text="Ex: quanto XP o Pack de XP concede")

    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} [{self.get_raridade_display()}] ({self.total_pecas} peças)"


class PecaRoleta(models.Model):
    item = models.ForeignKey(ItemColecionavel, on_delete=models.CASCADE, related_name="pecas_roleta")
    numero_peca = models.IntegerField(help_text="Qual peça do item (1..total_pecas)")
    peso_sorteio = models.IntegerField(default=10, help_text="Chance relativa (maior = mais comum)")
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"Peça {self.numero_peca} de {self.item.nome}"


class GiroRoletaLog(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    peca = models.ForeignKey(PecaRoleta, on_delete=models.SET_NULL, null=True)
    data_giro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} girou em {self.data_giro:%d/%m}"


# ══════════════════════════════════════════════════════════════════
# 7. INVENTÁRIO
# ══════════════════════════════════════════════════════════════════
class PecaInventario(models.Model):
    # Status da peça — resolve o bug de venda no mercado: antes, anunciar uma
    # peça não a "reservava", então dava pra montar o item OU anunciar de novo
    # a mesma peça enquanto ela estava à venda. Agora a peça à venda fica
    # marcada e sai das operações de montar/anunciar.
    class Status(models.TextChoices):
        DISPONIVEL = "DISPONIVEL", "Disponível"
        A_VENDA = "A_VENDA", "À venda no mercado"

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pecas")
    item = models.ForeignKey(ItemColecionavel, on_delete=models.CASCADE)
    numero_peca = models.IntegerField()
    origem = models.CharField(max_length=20, default="roleta")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DISPONIVEL)
    data = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username} tem peça {self.numero_peca} de {self.item.nome}"


class ItemInventario(models.Model):
    class Status(models.TextChoices):
        DISPONIVEL = "DISPONIVEL", "Disponível"
        A_VENDA = "A_VENDA", "À venda no mercado"
        RESGATADO = "RESGATADO", "Resgatado (usado)"

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(ItemColecionavel, on_delete=models.SET_NULL, null=True)
    nome_snapshot = models.CharField(max_length=100, help_text="Nome do item no momento")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DISPONIVEL)
    data_obtencao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.usuario.username}: {self.nome_snapshot} [{self.status}]"


# ══════════════════════════════════════════════════════════════════
# 8. LOJA OFICIAL
# ══════════════════════════════════════════════════════════════════
class ItemLojaOficial(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    preco_lc = models.IntegerField()
    icone = models.CharField(max_length=40, default="fa-store")
    estoque = models.IntegerField(default=-1, help_text="-1 = ilimitado")
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nome} — {self.preco_lc} LC"


class ResgateLojaOficial(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "PENDENTE", "Aguardando aprovação"
        ENTREGUE = "ENTREGUE", "Entregue"
        CANCELADO = "CANCELADO", "Cancelado / reembolsado"

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="resgates_oficiais")
    item = models.ForeignKey(ItemLojaOficial, on_delete=models.SET_NULL, null=True)
    custo_pago = models.IntegerField()
    data_resgate = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDENTE)

    def __str__(self):
        return f"{self.usuario.username} resgatou {self.item} por {self.custo_pago} LC"


# ══════════════════════════════════════════════════════════════════
# 9. MERCADO CLANDESTINO — técnicos vendem entre si
# ══════════════════════════════════════════════════════════════════
class AnuncioMercado(models.Model):
    class TipoConteudo(models.TextChoices):
        ITEM = "ITEM", "Item completo"
        PECA = "PECA", "Peça"

    class Status(models.TextChoices):
        ATIVO = "ATIVO", "À venda"
        VENDIDO = "VENDIDO", "Vendido"
        CANCELADO = "CANCELADO", "Cancelado"

    vendedor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="anuncios")
    tipo_conteudo = models.CharField(max_length=6, choices=TipoConteudo.choices)
    item_inventario = models.ForeignKey(ItemInventario, on_delete=models.CASCADE, null=True, blank=True)
    peca_inventario = models.ForeignKey(PecaInventario, on_delete=models.CASCADE, null=True, blank=True)
    preco_lc = models.IntegerField(help_text="Preço definido pelo vendedor")
    descricao_venda = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)
    data_criacao = models.DateTimeField(auto_now_add=True)
    comprador = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="compras")
    data_venda = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-data_criacao",)

    def __str__(self):
        return f"{self.vendedor.username} vende por {self.preco_lc} LC [{self.status}]"