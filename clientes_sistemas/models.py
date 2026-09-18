import re
import unicodedata
from django.db import models
from django.utils import timezone
from sistemas.models import Sistema
from datetime import timedelta  # <-- ADICIONE ESSA LINHA AQUI

# ... outros imports

class Cliente(models.Model):
    ABC_CHOICES = [
        ('A', 'A - Alta'),
        ('B', 'B - Média'),
        ('C', 'C - Baixa'),
        ('D', 'D - Muito Baixa'),
    ]

    FINANCEIRO_CHOICES = [
        ('EM_DIA', 'Em Dia'),
        ('PENDENTE', 'Pendente'),
    ]

    codigo = models.AutoField(primary_key=True)
    razao_social = models.CharField(max_length=255)
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True)
    cnpj = models.CharField(max_length=18, unique=True)
    inscricao_estadual = models.CharField(max_length=20, blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    # Endereço
    cep = models.CharField(max_length=9, blank=True, null=True)
    logradouro = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=20, blank=True, null=True)
    bairro = models.CharField(max_length=150, blank=True, null=True)
    cidade = models.CharField(max_length=150, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True)

    # Responsável
    nome_responsavel = models.CharField(max_length=255, blank=True, null=True)
    telefone_responsavel = models.CharField(max_length=20, blank=True, null=True)
    email_responsavel = models.EmailField(blank=True, null=True)

    # Classificação
    faturamento_cliente = models.CharField(max_length=1, choices=ABC_CHOICES, default='C')
    visibilidade_cliente = models.CharField(max_length=1, choices=ABC_CHOICES, default='C')

    # Status Financeiro
    status_financeiro = models.CharField(
        max_length=10, 
        choices=FINANCEIRO_CHOICES, 
        default='EM_DIA',
        verbose_name="Status Financeiro"
    )

    # ==========================================
    # CAMPO NOVO: Observações
    # ==========================================
    observacoes = models.TextField(
        verbose_name="Observações Internas", 
        blank=True, 
        null=True,
        help_text="Anotações importantes sobre este cliente que aparecerão no chat do bot."
    )

    # ==========================================
    # CAMPOS NOVOS: Regime Tributário e Data
    # ==========================================
    regime_tributario = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        verbose_name="Regime Tributário"
    )
    data_consulta_cnpj = models.DateTimeField(
        blank=True, 
        null=True, 
        verbose_name="Última Consulta de CNPJ"
    )

    # Serviços
    contrato_software = models.BooleanField(default=False)
    contrato_hardware = models.BooleanField(default=False)
    backup_contratado = models.BooleanField(default=False)
    hospedagem_datacenter = models.BooleanField(default=False)

    sistemas = models.ManyToManyField(Sistema, related_name="clientes", blank=True)
    serial_sistema = models.CharField(max_length=100, blank=True, null=True)
    ativo = models.BooleanField(default=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    # Health Score
    health_score = models.IntegerField(default=100, verbose_name="Saúde do Cliente")
    nivel_risco = models.CharField(
        max_length=20, 
        default='BAIXO',
        choices=[('BAIXO', 'Baixo Risco'), ('MEDIO', 'Risco Médio'), ('ALTO', 'Alto Risco'), ('CRITICO', 'Risco Crítico')]
    )
    data_ultimo_calculo = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["razao_social"]

    def save(self, *args, **kwargs):
        import unicodedata
        
        # PADRONIZAÇÃO DO CNPJ/CPF: Sempre salva com a máscara (Padrão Ouro)
        if self.cnpj:
            numeros = re.sub(r'\D', '', str(self.cnpj))
            if len(numeros) == 14:
                self.cnpj = f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
            elif len(numeros) == 11:
                self.cnpj = f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
            else:
                self.cnpj = numeros
                
        if self.telefone:
            self.telefone = re.sub(r'\D', '', str(self.telefone))
        if self.telefone_responsavel:
            self.telefone_responsavel = re.sub(r'\D', '', str(self.telefone_responsavel))
            
        # PADRONIZAÇÃO DE CIDADE MODO HARD: Sem espaços, MAIÚSCULO e SEM ACENTO
        if self.cidade:
            cidade_limpa = ''.join(c for c in unicodedata.normalize('NFD', str(self.cidade)) if unicodedata.category(c) != 'Mn')
            self.cidade = cidade_limpa.strip().upper()
            
        super().save(*args, **kwargs)

    def calcular_health_score(self):
        score = 100 
        agora = timezone.now()
        hoje = agora.date()

        # ======================================================================
        # 1. SAÚDE FINANCEIRA (Peso: Crítico)
        # ======================================================================
        if self.status_financeiro == 'PENDENTE':
            score -= 35

        # ======================================================================
        # 2. PERFORMANCE DO SUPORTE & SLA (Baseado no seu model Atendimento)
        # ======================================================================
        atendimentos = self.atendimento_set.all()
        
        # OSs que estão abertas agora "sangrando" a nota
        tickets_abertos = atendimentos.filter(status__in=['ABERTO', 'EM_ATENDIMENTO'])
        score -= (tickets_abertos.filter(prioridade='CRITICA').count() * 20)
        score -= (tickets_abertos.filter(prioridade='ALTA').count() * 10)
        score -= (tickets_abertos.filter(prioridade='MEDIA').count() * 5)

        # Penalidade por histórico de SLA (Últimos 30 dias)
        # Se a gente furou o prazo com o cliente recentemente, ele está irritado.
        atrasos_recentes = atendimentos.filter(
            data_conclusao__gte=agora - timedelta(days=30),
            resolvido_no_prazo=False
        ).count()
        score -= (atrasos_recentes * 7)

        # ======================================================================
        # 3. SENTIMENTO DO CLIENTE (Baseado no model ChatSession do WhatsApp)
        # ======================================================================
        try:
            from whatsapp_bot.models import ChatSession
            # Pega a última avaliação de NPS ou Técnico (últimos 60 dias)
            ultima_avaliacao = ChatSession.objects.filter(
                cliente=self,
                status='FINALIZADO'
            ).exclude(nota_nps__isnull=True).order_by('-ultima_interacao').first()

            if ultima_avaliacao:
                # Lógica NPS (0-10): Abaixo de 7 é detrator
                if ultima_avaliacao.nota_nps <= 6:
                    score -= 30 
                elif ultima_avaliacao.nota_nps >= 9:
                    score += 10 # Bônus para clientes promotores
                
                # Lógica Técnico (1-5): Nota 1 ou 2 é atrito pesado
                if ultima_avaliacao.nota_tecnico and ultima_avaliacao.nota_tecnico <= 2:
                    score -= 15
        except ImportError:
            pass

        # ======================================================================
        # 4. INTELIGÊNCIA DO CS (Timeline Manual)
        # ======================================================================
        eventos_recentes = self.eventos_cs.filter(
            data_realizada__gte=hoje - timedelta(days=90),
            status='REALIZADO'
        ).order_by('-data_realizada')

        if eventos_recentes.exists():
            for evento in eventos_recentes:
                # Punições por motivos de risco detectados pelo CS
                if evento.motivo_risco == 'CONCORRENCIA':
                    score -= 80  
                elif evento.motivo_risco in ['ATENDIMENTO', 'BUGS', 'FUNCIONALIDADE']:
                    score -= 40  
                elif evento.motivo_risco == 'FINANCEIRO':
                    score -= 20
                
                # Remédio: Ação de Retenção recupera a confiança
                if evento.tipo_contato == 'RETENCAO':
                    score += 40 
        else:
            # Cliente "No Escuro" (Sem contato do CS há > 90 dias)
            score -= 15

        # ======================================================================
        # FINALIZAÇÃO E SALVAMENTO
        # ======================================================================
        self.health_score = max(0, min(100, int(score)))
        self.data_ultimo_calculo = agora

        # Define a gravidade visual
        if self.health_score >= 80: self.nivel_risco = 'BAIXO'
        elif self.health_score >= 50: self.nivel_risco = 'MEDIO'
        elif self.health_score >= 30: self.nivel_risco = 'ALTO'
        else: self.nivel_risco = 'CRITICO'

        self.save(update_fields=['health_score', 'data_ultimo_calculo', 'nivel_risco'])
        
        return self.health_score

    def __str__(self):
        return f"{self.razao_social} - {self.cnpj}"