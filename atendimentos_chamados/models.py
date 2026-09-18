from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class Setor(models.Model):
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome


class Atendimento(models.Model):

    class Prioridade(models.TextChoices):
        BAIXA = "BAIXA", "Baixa"
        MEDIA = "MEDIA", "Média"
        ALTA = "ALTA", "Alta"
        CRITICA = "CRITICA", "Crítica"

    class Status(models.TextChoices):
        ABERTO = "ABERTO", "Aberto"
        EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em Atendimento"
        AGUARDANDO_CLIENTE = "AGUARDANDO_CLIENTE", "Aguardando Cliente"
        AGUARDANDO_DESENVOLVIMENTO = "AGUARDANDO_DESENVOLVIMENTO", "Aguardando Desenv."
        CONCLUIDO = "CONCLUIDO", "Concluído"

    class TipoTreinamento(models.TextChoices):
        ONLINE = "ONLINE", "Online"
        PRESENCIAL = "PRESENCIAL", "Presencial"

    numero = models.AutoField(primary_key=True)

    cliente = models.ForeignKey(
        "clientes_sistemas.Cliente",
        on_delete=models.CASCADE
    )

    numero_os = models.CharField(max_length=100, blank=True, null=True)

    titulo = models.CharField(max_length=255)
    descricao = models.TextField()

    prioridade = models.CharField(max_length=10, choices=Prioridade.choices)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ABERTO)

    setor_atual = models.ForeignKey(
        Setor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="atendimentos"
    )

    tecnico_responsavel = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    implantacao_cliente_novo = models.BooleanField(default=False)
    implantacao_modulo_novo = models.BooleanField(default=False)

    possui_treinamento = models.BooleanField(default=False)
    tipo_treinamento = models.CharField(
        max_length=15,
        choices=TipoTreinamento.choices,
        blank=True,
        null=True
    )

    abrir_cs_pos_atendimento = models.BooleanField(default=False)

    # ==========================================
    # NOVOS CAMPOS: ESCOPO E TREINAMENTO
    # ==========================================
    whatsapp_contato = models.CharField(max_length=50, blank=True, null=True, help_text="WhatsApp de quem vai acompanhar a implantação")
    
    # Parâmetros de Implantação
    flag_conversao_dados = models.BooleanField(default=False)
    flag_instalacao_equip = models.BooleanField(default=False)
    flag_tef_incluso = models.BooleanField(default=False)
    flag_mobilidade = models.BooleanField(default=False)
    flag_backup = models.BooleanField(default=False)
    flag_data_center = models.BooleanField(default=False)
    
    # Módulos de Treinamento Contratados
    trein_cadastros = models.BooleanField(default=False, verbose_name="Cadastros e Estoque")
    trein_entrada_nf = models.BooleanField(default=False, verbose_name="Entrada de NF")
    trein_saida_nf = models.BooleanField(default=False, verbose_name="Saída de NF")
    trein_nfce = models.BooleanField(default=False, verbose_name="Cupom NFC-e")
    trein_estoque = models.BooleanField(default=False, verbose_name="Controle de Estoque")
    trein_financeiro = models.BooleanField(default=False, verbose_name="Módulo Financeiro")
    trein_boletos = models.BooleanField(default=False, verbose_name="Emissão de Boletos")
    trein_os_service = models.BooleanField(default=False, verbose_name="OS-Service")



    data_abertura = models.DateTimeField(default=timezone.now)
    data_conclusao = models.DateTimeField(null=True, blank=True)

    sla_horas = models.IntegerField(default=24)
    resolvido_no_prazo = models.BooleanField(default=False)

    # ==========================================
    # 1. GUARDA O ESTADO ORIGINAL (TÉCNICO E SETOR)
    # ==========================================
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tecnico_original_id = self.tecnico_responsavel_id
        self._setor_original_id = self.setor_atual_id

    def definir_sla(self):
        mapa = {
            "CRITICA": 4,
            "ALTA": 8,
            "MEDIA": 24,
            "BAIXA": 48,
        }
        self.sla_horas = mapa.get(self.prioridade, 24)

    def calcular_sla(self):
        limite = self.data_abertura + timedelta(hours=self.sla_horas)
        if self.data_conclusao:
            self.resolvido_no_prazo = self.data_conclusao <= limite

    def gerar_cs_pos_atendimento(self):
        from cs_satisfacao.models import EventoCS

        # Evita duplicação
        if EventoCS.objects.filter(origem_atendimento=self).exists():
            return

        EventoCS.objects.create(
            cliente=self.cliente,
            origem_atendimento=self,
            responsavel=self.tecnico_responsavel,
            data_prevista=(timezone.now() + timedelta(days=7)).date(),
        )

    # ==========================================
    # 2. INTERCEPTA O SALVAMENTO E OS GATILHOS
    # ==========================================
    def save(self, *args, **kwargs):
        status_anterior = None
        if self.pk:
            status_anterior = Atendimento.objects.get(pk=self.pk).status

        self.definir_sla()

        if self.status == self.Status.CONCLUIDO:
            if not self.data_conclusao:
                self.data_conclusao = timezone.now()
            self.calcular_sla()

        # Gatilhos para o Celery (WhatsApp)
        tecnico_foi_alterado = False
        setor_foi_alterado_sem_tecnico = False

        if self.pk:
            # 1. Avalia se atribuíram/trocaram o técnico
            if self.tecnico_responsavel_id != self._tecnico_original_id and self.tecnico_responsavel_id is not None:
                tecnico_foi_alterado = True
            
            # 2. Avalia se mudaram a fila (setor) E a OS continua sem técnico
            if self.setor_atual_id != self._setor_original_id and self.tecnico_responsavel_id is None:
                setor_foi_alterado_sem_tecnico = True
        else:
            # Caso seja uma OS nova (sendo criada agora)
            if self.tecnico_responsavel_id is not None:
                tecnico_foi_alterado = True
            elif self.setor_atual_id is not None:
                setor_foi_alterado_sem_tecnico = True

        super().save(*args, **kwargs)

        # Atualiza a referência em memória após o salvamento para evitar loops
        self._tecnico_original_id = self.tecnico_responsavel_id
        self._setor_original_id = self.setor_atual_id

        # 🔥 Pós save — gera CS se acabou de concluir
        if (
            self.status == self.Status.CONCLUIDO and
            status_anterior != self.Status.CONCLUIDO and
            self.abrir_cs_pos_atendimento
        ):
            self.gerar_cs_pos_atendimento()

        # 🔥 Pós save — Dispara o aviso para o Técnico via WhatsApp (Celery)
        if tecnico_foi_alterado:
            try:
                from calendario_agenda.tasks import notify_tecnico_novo_atendimento
                notify_tecnico_novo_atendimento.delay(self.pk)
            except Exception as e:
                print(f"Erro ao agendar notificação via WhatsApp (Técnico): {e}")

        # 🔥 Pós save — Dispara o aviso para o SETOR INTEIRO via WhatsApp (Celery)
        if setor_foi_alterado_sem_tecnico:
            try:
                from calendario_agenda.tasks import notify_setor_novo_atendimento
                notify_setor_novo_atendimento.delay(self.pk)
            except Exception as e:
                print(f"Erro ao agendar notificação via WhatsApp (Setor Broadcast): {e}")

    def __str__(self):
        return f"{self.numero} - {self.titulo}"


class AtendimentoHistorico(models.Model):
    atendimento = models.ForeignKey(
        Atendimento,
        on_delete=models.CASCADE,
        related_name="historico"
    )

    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    setor = models.ForeignKey(Setor, on_delete=models.SET_NULL, null=True)
    comentario = models.TextField(blank=True, null=True)

    data = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Histórico #{self.atendimento.numero}"