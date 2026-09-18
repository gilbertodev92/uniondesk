import uuid
import re
import datetime
from django.db import models
from django.contrib.auth.models import User
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

# ==========================================
# 1. AUXILIARES DO CRM
# ==========================================

class MotivoPerda(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Motivo de Perda"
        verbose_name_plural = "Motivos de Perda"

    def __str__(self):
        return self.nome

class MotivoExcecaoSLA(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Motivo de Exceção SLA"
        verbose_name_plural = "Motivos de Exceção SLA"

    def __str__(self):
        return self.nome

class Segmento(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    ativo = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['nome']
        
    def __str__(self):
        return self.nome

# ==========================================
# 2. O CORAÇÃO DO SALES MONSTER
# ==========================================

class Lead(models.Model):
    ETAPAS_CHOICES = [
        ('0_PROSPECCAO', '0. Mesa de Prospecção'),
        ('1_LEAD', '1. Lead Recebido'),
        ('2_CONTATO', '2. Primeiro Contato / Qualificação'),
        ('3_DIAGNOSTICO', '3. Diagnóstico Técnico'),
        ('4_PROPOSTA', '4. Proposta Enviada'),
        ('5_NEGOCIACAO', '5. Negociação'),
        ('6_GANHO', '6. Ganho'),
        ('7_PERDIDO', '7. Perdido'),
    ]

    ORIGEM_CHOICES = [
        ('SITE', 'Site'),
        ('INDICACAO_CONTABIL', 'Indicação Contábil'),
        ('INDICACAO_CLIENTE', 'Indicação Cliente'),
        ('GOOGLE', 'Google'),
        ('WHATSAPP', 'Whatsapp'),
        ('LIGACAO', 'Ligação'),
        ('VISITA_CLIENTE', 'Visita do Cliente'),
        ('VISITA_AO_CLIENTE', 'Visita ao Cliente'),
        ('RECICLAGEM', 'Reciclagem'), 
    ]

    URGENCIA_CHOICES = [
        ('ALTA', 'Alta'),
        ('MEDIA', 'Média'),
        ('BAIXA', 'Baixa'),
    ]

    STATUS_SLA_CHOICES = [
        ('VERDE', 'Dentro do Prazo'),
        ('AMARELO', 'Atenção'),
        ('LARANJA', 'Exceção / Aguardando'),
        ('VERMELHO', 'Atrasado / Alerta'),
    ]

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    cnpj = models.CharField(max_length=18, blank=True, null=True, verbose_name="CNPJ")
    nome_empresa = models.CharField(max_length=150)
    nome_contato = models.CharField(max_length=150)
    telefone = models.CharField(max_length=20)
    cidade = models.CharField(max_length=100)
    segmento = models.ForeignKey(Segmento, on_delete=models.SET_NULL, null=True, blank=True) 
    origem = models.CharField(max_length=50, choices=ORIGEM_CHOICES)
    ativo = models.BooleanField(default=True) 
    
    etapa = models.CharField(max_length=30, choices=ETAPAS_CHOICES, default='0_PROSPECCAO')
    vendedor_responsavel = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='meus_leads')
    
    vendedor_prospeccao = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='minhas_prospeccoes')
    data_prospeccao = models.DateTimeField(null=True, blank=True)
    observacao_rapida = models.TextField(blank=True, null=True) 
    resgatar_reciclagem = models.BooleanField(default=False)
    data_prevista_reciclagem = models.DateField(null=True, blank=True)
    
    dor_principal = models.TextField(blank=True, null=True)
    necessidade_desejo = models.TextField(blank=True, null=True)
    urgencia = models.CharField(max_length=10, choices=URGENCIA_CHOICES, default='MEDIA')

    forma_pagamento = models.CharField(max_length=150, blank=True, null=True)
    prazo_pagamento = models.CharField(max_length=150, blank=True, null=True)

    valor_equipamentos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    valor_mensalidade = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    valor_servicos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    data_criacao = models.DateTimeField(auto_now_add=True)
    ultima_atualizacao = models.DateTimeField(auto_now=True)
    data_limite_proximo_contato = models.DateTimeField(null=True, blank=True)
    status_sla = models.CharField(max_length=15, choices=STATUS_SLA_CHOICES, default='VERDE')
    
    data_entrada_etapa = models.DateTimeField(default=timezone.now)
    data_limite_sla = models.DateTimeField(null=True, blank=True) 
    motivo_extensao_sla = models.TextField(blank=True, null=True)
    
    motivo_excecao = models.ForeignKey(MotivoExcecaoSLA, on_delete=models.SET_NULL, null=True, blank=True)
    justificativa_excecao = models.TextField(blank=True, null=True)

    motivo_perda = models.ForeignKey(MotivoPerda, on_delete=models.SET_NULL, null=True, blank=True)
    detalhe_perda = models.TextField(blank=True, null=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    
    cliente_existente = models.ForeignKey('clientes_sistemas.Cliente', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Lead"
        verbose_name_plural = "Leads"
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.nome_empresa} ({self.nome_contato})"

    @property
    def valor_ticket_medio(self):
        return self.valor_equipamentos + self.valor_mensalidade + self.valor_servicos

    def save(self, *args, **kwargs):
        if self.cnpj:
            self.cnpj = re.sub(r'\D', '', str(self.cnpj))
        if self.telefone:
            self.telefone = re.sub(r'\D', '', str(self.telefone))
            
        # PADRONIZAÇÃO DE CIDADE: Remove espaços extras e joga tudo pra MAIÚSCULO
        if self.cidade:
            self.cidade = str(self.cidade).strip().upper()
            
        HORA_ABERTURA = 8
        HORA_FECHAMENTO = 18

        # LÓGICA BLINDADA AQUI
        if self._state.adding or self._etapa_mudou():
            agora = timezone.now()
            self.data_entrada_etapa = agora
            
            if self.etapa == '1_LEAD':
                prazo = agora
                horas_a_add = 4
                while horas_a_add > 0:
                    prazo += datetime.timedelta(hours=1)
                    if prazo.hour >= HORA_FECHAMENTO or prazo.weekday() >= 5:
                        prazo = prazo.replace(hour=HORA_ABERTURA) + datetime.timedelta(days=1)
                        if prazo.weekday() == 5: prazo += datetime.timedelta(days=2) 
                        if prazo.weekday() == 6: prazo += datetime.timedelta(days=1) 
                    horas_a_add -= 1
                self.data_limite_sla = prazo
            elif self.etapa not in ['0_PROSPECCAO', '6_GANHO', '7_PERDIDO']:
                self.data_limite_sla = agora + datetime.timedelta(hours=24)
            else:
                self.data_limite_sla = None

        super().save(*args, **kwargs)

    def _etapa_mudou(self):
        # A MÁGICA DE SEGURANÇA: Se for novo, não procura no banco
        if self._state.adding:
            return True
        try:
            obj_antigo = Lead.objects.get(pk=self.pk)
            return obj_antigo.etapa != self.etapa
        except Lead.DoesNotExist:
            return True

    @property
    def esta_atrasado(self):
        if self.etapa in ['0_PROSPECCAO', '6_GANHO', '7_PERDIDO']: return False
        return timezone.now() > self.data_limite_sla if self.data_limite_sla else False

    @property
    def tempo_restante_formatado(self):
        if not self.data_limite_sla: return ""
        agora = timezone.now()
        diff = self.data_limite_sla - agora
        if diff.total_seconds() < 0:
            total_horas = int(abs(diff.total_seconds()) // 3600)
            return f"Atrasado {total_horas}h"
        return f"{int(diff.total_seconds() // 3600)}h restantes"

    # ══════════════════════════════════════════════════════════════════
    # VALORES — venda única vs. recorrente
    #
    # `valor_ticket_medio` (acima) soma equipamento + serviço + MENSALIDADE
    # no mesmo número. Isso infla o funil: R$ 1.000 de equipamento com
    # R$ 200/mês vira "R$ 1.200", misturando dinheiro que entra UMA vez
    # com dinheiro que entra TODO mês.
    # As duas propriedades abaixo separam. O campo antigo continua
    # existindo para não quebrar nada que já o utilize.
    # ══════════════════════════════════════════════════════════════════

    @property
    def valor_venda_unica(self):
        """Dinheiro que entra uma vez só: equipamentos + serviços."""
        return (self.valor_equipamentos or 0) + (self.valor_servicos or 0)

    @property
    def valor_recorrente(self):
        """Dinheiro que entra todo mês."""
        return self.valor_mensalidade or 0

    # ══════════════════════════════════════════════════════════════════
    # SLA POR INATIVIDADE
    #
    # O SLA antigo media TEMPO NA ETAPA. Resultado: um lead em "Primeiro
    # Contato" há 21 dias acusava "Atrasado 502h" mesmo que o vendedor
    # tivesse falado com ele ontem. Como TODO cartão ficava vermelho, o
    # alerta perdeu a função — ninguém mais olhava.
    #
    # Agora medimos TEMPO SEM INTERAÇÃO: qualquer anotação registrada
    # reinicia o relógio. O vermelho volta a significar uma coisa só —
    # "ninguém tocou nisto" — que é o que o gestor precisa enxergar.
    # ══════════════════════════════════════════════════════════════════

    # Dias tolerados sem interação, por etapa. Ajuste conforme a operação.
    LIMITE_DIAS_SEM_CONTATO = {
        '1_LEAD':         1,   # lead novo é urgente
        '2_CONTATO':      3,
        '3_DIAGNOSTICO':  5,
        '4_PROPOSTA':     7,   # proposta em análise leva tempo, é normal
        '5_NEGOCIACAO':   5,
    }

    @property
    def ultima_interacao(self):
        """Data da última movimentação real (entrada na etapa ou anotação)."""
        referencia = self.data_entrada_etapa or self.data_criacao
        try:
            ultima_nota = self.anotacoes.first()  # ordering = ['-data_criacao']
            if ultima_nota and ultima_nota.data_criacao and ultima_nota.data_criacao > referencia:
                referencia = ultima_nota.data_criacao
        except Exception:
            pass
        return referencia

    @property
    def dias_parado(self):
        """Dias inteiros desde a última interação."""
        ref = self.ultima_interacao
        if not ref:
            return 0
        return max(0, (timezone.now() - ref).days)

    @property
    def nivel_atencao(self):
        """'ok' | 'atencao' | 'critico' — usado para colorir o cartão."""
        if self.etapa in ['0_PROSPECCAO', '6_GANHO', '7_PERDIDO']:
            return 'ok'
        limite = self.LIMITE_DIAS_SEM_CONTATO.get(self.etapa, 5)
        dias = self.dias_parado
        if dias >= limite:
            return 'critico'
        if dias >= max(1, int(limite * 0.6)):
            return 'atencao'
        return 'ok'

    @property
    def rotulo_parado(self):
        """
        Texto curto do selo no cartão. Com teto: em vez de "Atrasado 502h"
        (que não diz nada), mostra "12 dias" e, acima de 30, "30d+".
        """
        dias = self.dias_parado
        if dias == 0:
            return "hoje"
        if dias == 1:
            return "1 dia"
        if dias > 30:
            return "30d+"
        return f"{dias} dias"

    @property
    def rotulo_parado_titulo(self):
        """Texto completo exibido ao passar o mouse sobre o selo."""
        dias = self.dias_parado
        limite = self.LIMITE_DIAS_SEM_CONTATO.get(self.etapa, 5)
        if dias == 0:
            return "Teve interação hoje"
        base = f"Sem interação há {dias} dia{'s' if dias > 1 else ''}"
        if self.nivel_atencao == 'critico':
            return f"{base} — o limite desta etapa é {limite} dia{'s' if limite > 1 else ''}"
        return base



class ItemProposta(models.Model):
    TIPO_CHOICES = [
        ('PRODUTO', 'Produto / Equipamento'),
        ('SERVICO', 'Serviço / Implantação'),
        ('MENSALIDADE', 'Licença / Mensalidade'),
    ]
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='itens_proposta')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    nome = models.CharField(max_length=200)
    quantidade = models.PositiveIntegerField(default=1) # O campo que adicionamos antes
    valor = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['tipo', 'nome']

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.nome} - R$ {self.valor}"

    # 🔥 NOVO: Motor de matemática blindado!
    @property
    def subtotal(self):
        return self.valor * self.quantidade
    
# ==========================================
# 3. AUDITORIA E ARQUIVOS
# ==========================================
class HistoricoMovimentacao(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='historico')
    data_hora = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    acao = models.CharField(max_length=255)
    detalhes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-data_hora']

class AnotacaoLead(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='anotacoes')
    vendedor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    texto = models.TextField()
    etapa_no_momento = models.CharField(max_length=500)
    data_criacao = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-data_criacao']

class VendaPessoal(models.Model):
    TIPO_CHOICES = (
        ('EQUIPAMENTO', 'Equipamento'),
        ('SERVICO', 'Serviço'),
    )
    vendedor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vendas_pessoais')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    descricao = models.CharField(max_length=255)
    data_venda = models.DateField(default=timezone.now)

    def __str__(self):
        return f"{self.get_tipo_display()} - R$ {self.valor}"

class MetaUsuario(models.Model):
    vendedor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='metas')
    mes = models.IntegerField()
    ano = models.IntegerField()
    valor_meta = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('vendedor', 'mes', 'ano')

class ArquivoProposta(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='arquivos')
    arquivo = models.FileField(upload_to='crm/propostas/%Y/%m/')
    nome_arquivo = models.CharField(max_length=255)
    data_upload = models.DateTimeField(auto_now_add=True)
    vendedor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.nome_arquivo