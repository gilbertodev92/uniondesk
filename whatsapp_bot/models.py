from django.db import models
from django.contrib.auth import get_user_model
from clientes_sistemas.models import Cliente 

User = get_user_model()

class TagAtendimento(models.Model):
    nome = models.CharField(max_length=50)
    cor = models.CharField(max_length=7, default="#6366f1")

    def __str__(self):
        return self.nome

class MensagemRapida(models.Model):
    titulo = models.CharField(max_length=100, help_text="Ex: Saudação Bom Dia")
    atalho = models.CharField(max_length=30, unique=True, help_text="Ex: /bomdia")
    texto = models.TextField(help_text="Use {nome} para inserir o nome do atendente automaticamente na mensagem.")

    class Meta:
        ordering = ['atalho']

    def __str__(self):
        return f"{self.atalho} - {self.titulo}"

class ChatSession(models.Model):
    STATUS_CHOICES = [
        ('TRIAGEM', 'Em Triagem pela IA (Recepção)'),
        ('SUPORTE_IA', 'Em Atendimento pela IA (Analista Digital)'),
        ('PENDENTE', 'Aguardando Técnico Humano'),
        ('EM_ATENDIMENTO', 'Em Atendimento Humano'),
        ('AVALIACAO_TECNICO', 'Aguardando Nota do Técnico (1-5)'),
        ('AVALIACAO_NPS', 'Aguardando Nota da Empresa (0-10)'),
        ('FINALIZADO', 'Atendimento Encerrado'),
    ]

    SETOR_CHOICES = [
        ('TRIAGEM', 'Triagem'),
        ('SUPORTE', 'Suporte Sistemas'),
        ('FINANCEIRO', 'Financeiro'),
        ('COMERCIAL', 'Comercial / Vendas'),
        ('ASSISTENCIA', 'Assistência Técnica'),
    ]

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    whatsapp_number = models.CharField(max_length=100) 
    push_name = models.CharField(max_length=255, null=True, blank=True) 
    profile_pic = models.URLField(max_length=1000, null=True, blank=True) 
    
    tecnico_responsavel = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TRIAGEM')
    setor_atual = models.CharField(max_length=20, choices=SETOR_CHOICES, default='TRIAGEM')
    em_atendimento_ia = models.BooleanField(default=True)
    
    tentativas_ia = models.IntegerField(default=0)
    
    nota_tecnico = models.IntegerField(null=True, blank=True) 
    nota_nps = models.IntegerField(null=True, blank=True)     
    
    tags = models.ManyToManyField(TagAtendimento, blank=True)
    mensagens_nao_lidas = models.IntegerField(default=0)
    
    data_inicio = models.DateTimeField(auto_now_add=True)
    ultima_interacao = models.DateTimeField(auto_now=True)

    def __str__(self):
        nome = self.cliente.razao_social if self.cliente else self.push_name or self.whatsapp_number
        return f"{nome} - {self.get_status_display()}"

class Message(models.Model):
    SENDER_CHOICES = [
        ('CLIENTE', 'Cliente'),
        ('IA', 'IA'),
        ('TECNICO', 'Técnico'),
        ('SISTEMA', 'Sistema'),
        ('INTERNO', 'Comentário Interno'),
    ]
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender_type = models.CharField(max_length=10, choices=SENDER_CHOICES)
    text = models.TextField()
    
    media_url = models.TextField(null=True, blank=True)
    message_id = models.CharField(max_length=255, null=True, blank=True) 
    quoted_message_id = models.CharField(max_length=255, null=True, blank=True)
    quoted_text = models.TextField(null=True, blank=True)
    
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    
    # === AQUI ESTÁ A MÁGICA DAS BOLINHAS ===
    ack = models.IntegerField(default=0, help_text="0=Pendente, 1=Enviado, 2=Entregue, 3=Lido, 4=Tocado")
    # ========================================
    
    tecnico = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Msg em {self.session.whatsapp_number} por {self.sender_type}"

class BotConfig(models.Model):
    chave_api_gemini = models.CharField(max_length=255)
    
    horario_inicio_semana = models.TimeField(default="07:30")
    horario_fim_semana = models.TimeField(default="20:00")
    horario_inicio_sabado = models.TimeField(default="07:30")
    horario_fim_sabado = models.TimeField(default="17:30")

# ── Identidade e regras (editáveis sem mexer em código) ──────────
    identidade_empresa = models.TextField(
        blank=True, null=True,
        verbose_name="Identidade da Empresa",
        help_text="Quem somos, o que vendemos. Vai no prompt da IA. "
                  "Deixe vazio para usar o padrão do sistema.",
    )
    regras_negocio = models.TextField(
        blank=True, null=True,
        verbose_name="Regras de Negócio",
        help_text="Regras específicas (links de boleto, políticas...). "
                  "Uma por linha. Deixe vazio para usar o padrão.",
    )

    # ── Áudio (TTS) ──────────────────────────────────────────────────
    modelo_tts = models.CharField(
        max_length=100, blank=True, default="gemini-2.5-flash-preview-tts",
        verbose_name="Modelo de Voz (TTS)",
        help_text="Ex: gemini-2.5-flash-preview-tts ou gemini-3.1-flash-tts-preview",
    )
    voz_tts = models.CharField(
        max_length=50, blank=True, default="Vindemiatrix",
        verbose_name="Voz da IA",
        help_text="Nome da voz do Gemini. Veja a lista de opções no guia.",
    )

    modelo_ia = models.CharField(
        max_length=100,
        default="gemini-flash-latest",
        help_text="Modelo Gemini usado pela IA (ex: gemini-flash-latest, "
                  "gemini-3.5-flash, gemini-2.5-flash). Troque aqui pra testar "
                  "outro modelo sem mexer no código.",
    )

    mensagem_saudacao = models.TextField(default="Olá! Sou a assistente virtual da Lógica Mais. Como posso te ajudar?")
    prompt_ia_triagem = models.TextField(
        default="Você é a recepcionista da Lógica Mais. Classifique o pedido do cliente nos setores: "
                "SUPORTE, ASSISTENCIA, COMERCIAL ou FINANCEIRO. Responda APENAS com o nome do setor."
    )

    mensagem_fora_horario = models.TextField(
        default="Nossos técnicos estão descansando agora, mas eu sou o Analista Digital da Lógica Mais! "
                "Posso tentar analisar seu erro e resolvermos juntos agora mesmo, o que acha?"
    )
    prompt_analista_digital = models.TextField(
        default="Você é um Analista de Sistemas da Lógica Mais. Seja técnico, resolva problemas baseando-se nas instruções fornecidas."
    )
    instrucoes_suporte_24h = models.TextField(
        blank=True, null=True,
        help_text="Cole aqui as soluções dos problemas mais comuns, senhas de reset, links, etc."
    )

    class Meta:
        verbose_name = "Configuração do Bot"

    def __str__(self):
        return "Configuração Global do Bot"