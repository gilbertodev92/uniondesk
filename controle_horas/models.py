# controle_horas/models.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, date
from django.contrib.auth.models import User
from django.conf import settings
from django.db import models

# ---- feriados automáticos (python-holidays) ----
try:
    import holidays as _hol
except Exception:
    _hol = None


def _is_feriado_auto(d: date) -> bool:
    """
    True se 'd' for feriado (nacional/estadual) usando a lib 'holidays'.
    Se a dependência não existir ou der erro -> False.
    Customize em settings.py (opcionais):
        FERIADOS_COUNTRY = "BR"
        FERIADOS_SUBDIV  = "PR"  # UF (SP, RJ, PR, ...)
    """
    if _hol is None:
        return False
    country = getattr(settings, "FERIADOS_COUNTRY", "BR")
    subdiv = getattr(settings, "FERIADOS_SUBDIV", None)
    try:
        if country == "BR":
            cal = _hol.Brazil(years=[d.year], subdiv=subdiv)
        else:
            cal = _hol.country_holidays(country=country, years=[d.year], subdiv=subdiv)
        return d in cal
    except Exception:
        return False


class ConfigHoras(models.Model):
    horas_dia = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("8.00"),
        help_text="Carga diária em horas decimais (ex.: 8.00, 8.80)."
    )
    pausa_almoco_min = models.PositiveIntegerField(
        default=60, help_text="Pausa padrão em minutos (ex.: 72 para 1h12)."
    )
    considerar_sabado = models.BooleanField(default=False)
    considerar_domingo = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuração de Horas"
        verbose_name_plural = "Configurações de Horas"

    def __str__(self):
        return f"Config ativa={self.ativo} (horas_dia={self.horas_dia}, pausa={self.pausa_almoco_min}min)"

    @classmethod
    def atual(cls):
        """Retorna a configuração ativa (ou None)."""
        return cls.objects.filter(ativo=True).order_by("-id").first()


class Apontamento(models.Model):
    # Tipos
    TIPO_NORMAL = "normal"
    TIPO_PLANTAO = "plantao"
    TIPO_ATUALIZACAO = "atualizacao"
    TIPO_EMERGENCIA = "emergencia"
    TIPO_IMPLANTACAO = "implantacao"
    TIPOS = [
        (TIPO_NORMAL, "Normal (4 marcações)"),
        (TIPO_PLANTAO, "Plantão (2 marcações)"),
        (TIPO_ATUALIZACAO, "Atualização (2 marcações)"),
        (TIPO_EMERGENCIA, "Atendimento Emergência (2 marcações)"),
        (TIPO_IMPLANTACAO, "Implantação (2 marcações)"),
    ]

    # Status
    ST_RASCUNHO = "rascunho"
    ST_PENDENTE = "pendente"
    ST_APROVADO = "aprovado"
    ST_REPROVADO = "reprovado"
    STATUS = [
        (ST_RASCUNHO, "Rascunho"),
        (ST_PENDENTE, "Pendente"),
        (ST_APROVADO, "Aprovado"),
        (ST_REPROVADO, "Reprovado"),
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    data = models.DateField()

    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_NORMAL)

    # Marcações (Normal = 4 pontos)
    manha_inicio = models.TimeField(null=True, blank=True)
    manha_fim = models.TimeField(null=True, blank=True)
    tarde_inicio = models.TimeField(null=True, blank=True)
    tarde_fim = models.TimeField(null=True, blank=True)

    # Marcações (Especiais = 2 pontos)
    especial_inicio = models.TimeField(null=True, blank=True)
    especial_fim = models.TimeField(null=True, blank=True)

    # ==========================================
    # CAMPO NOVO: Cliente vinculado (Atualização)
    # ==========================================
    cliente_atualizacao = models.ForeignKey(
        'clientes_sistemas.Cliente',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='apontamentos_atualizacao',
        verbose_name="Cliente (Atualização)",
        help_text="Preenchido quando tipo='atualizacao': qual cliente foi atualizado."
    )

    # Totais internos (em HORAS decimais)
    horas_total = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"), editable=False)
    horas_extra = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"), editable=False)

    # Campos auxiliares
    descricao = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS, default=ST_RASCUNHO)
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, related_name="aprovacoes_controle_horas",
        on_delete=models.SET_NULL
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-data", "-atualizado_em")
        indexes = [
            models.Index(fields=["usuario", "data"]),
            models.Index(fields=["status", "data"]),
        ]

    def __str__(self):
        return f"{self.usuario} {self.data} ({self.get_tipo_display()})"

    # -------------------------------
    # Cálculo de horas
    # -------------------------------
    @staticmethod
    def _delta_to_hours_decimal(delta: timedelta) -> Decimal:
        """Converte timedelta para horas decimais (2 casas), sem negativos."""
        total_minutes = Decimal(delta.total_seconds()) / Decimal(60)
        horas = (total_minutes / Decimal(60)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return max(horas, Decimal("0.00"))

    def _calc_total_trabalhado(self) -> Decimal:
        """
        Retorna horas trabalhadas em horas decimais:
        - Resolve o bug de virada de noite (ex: 23:00 às 02:00)
        """
        total = timedelta(0)

        def calcula_diff(inicio, fim):
            if not inicio or not fim:
                return timedelta(0)
            dt_inicio = datetime.combine(self.data, inicio)
            dt_fim = datetime.combine(self.data, fim)
            if dt_fim < dt_inicio:
                dt_fim += timedelta(days=1)
            return dt_fim - dt_inicio

        if self.tipo == self.TIPO_NORMAL:
            total += calcula_diff(self.manha_inicio, self.manha_fim)
            total += calcula_diff(self.tarde_inicio, self.tarde_fim)
        else:
            total += calcula_diff(self.especial_inicio, self.especial_fim)

        return self._delta_to_hours_decimal(total)

    def _carga_diaria_config(self) -> Decimal:
        """
        Carga diária alvo. Busca da ConfigHoras ativa.
        Se não houver, assume 8.80h (08:00–12:00 / 13:12–18:00 = 8h48).
        """
        cfg = ConfigHoras.atual()
        if cfg and cfg.horas_dia:
            return Decimal(cfg.horas_dia).quantize(Decimal("0.01"))
        return Decimal("8.80")

    def recomputa_totais(self):
        """
        Calcula APENAS horas_total deste registro (tempo efetivamente
        trabalhado). horas_extra NÃO é mais calculada aqui -- ela é
        recalculada em nível de DIA por `recalcular_extras_do_dia()`,
        chamada depois do save().
        """
        self.horas_total = self._calc_total_trabalhado().quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        self.recomputa_totais()
        super().save(*args, **kwargs)

        # Após salvar este registro, recalcula a extra de TODOS os
        # registros do mesmo usuário/data (pode ter mudado o total do dia).
        self._recalcular_extras_do_dia()

    def _recalcular_extras_do_dia(self):
        """
        Soma horas_total de todos os registros do usuário nesta data,
        compara com a meta diária e distribui a extra entre os registros,
        do mais antigo para o mais novo (os últimos registros do dia
        "absorvem" a extra primeiro).
        """
        cfg = ConfigHoras.atual()
        horas_dia = self._carga_diaria_config()
        considerar_sab = bool(cfg and cfg.considerar_sabado)
        considerar_dom = bool(cfg and cfg.considerar_domingo)

        wd = self.data.weekday()  # 0=seg ... 5=sáb, 6=dom
        feriado = _is_feriado_auto(self.data)

        # Em dia "fora da meta" (fim de semana não considerado / feriado),
        # TODAS as horas trabalhadas no dia são extra.
        dia_fora_da_meta = feriado or (wd == 5 and not considerar_sab) or (wd == 6 and not considerar_dom)

        registros_do_dia = list(
            Apontamento.objects.filter(
                usuario=self.usuario, data=self.data
            ).order_by("criado_em", "id")
        )

        if not registros_do_dia:
            return

        if dia_fora_da_meta:
            # Tudo é extra, registro por registro -- não precisa distribuir
            for r in registros_do_dia:
                nova_extra = r.horas_total
                if r.horas_extra != nova_extra:
                    Apontamento.objects.filter(pk=r.pk).update(horas_extra=nova_extra)
            return

        # Dia normal: soma o total do dia e compara com a meta
        total_dia = sum((r.horas_total for r in registros_do_dia), Decimal("0.00"))
        extra_total_dia = total_dia - horas_dia
        if extra_total_dia < Decimal("0.00"):
            extra_total_dia = Decimal("0.00")

        # Distribui a extra: percorre os registros do dia, do mais antigo
        # ao mais novo, preenchendo primeiro a "meta normal" e deixando
        # o excedente para os últimos registros.
        meta_restante = horas_dia
        extra_restante = extra_total_dia

        for r in registros_do_dia:
            worked = r.horas_total

            if meta_restante > 0:
                consumido_pela_meta = min(worked, meta_restante)
                meta_restante -= consumido_pela_meta
                excedente = worked - consumido_pela_meta
            else:
                excedente = worked

            nova_extra = excedente.quantize(Decimal("0.01"))

            if r.horas_extra != nova_extra:
                Apontamento.objects.filter(pk=r.pk).update(horas_extra=nova_extra)


class FechamentoMensal(models.Model):
    """
    Marca o fechamento da competência (mês/ano) por usuário.
    A competência é representada pelo 1º dia do mês.
    """
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fechamentos_mensais",
    )
    competencia = models.DateField(
        help_text="Use o primeiro dia do mês (ex.: 2025-10-01 para out/2025)."
    )

    fechado = models.BooleanField(default=False)
    fechado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="fechamentos_realizados",
    )
    fechado_em = models.DateTimeField(null=True, blank=True)

    observacao = models.TextField(blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fechamento Mensal"
        verbose_name_plural = "Fechamentos Mensais"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "competencia"],
                name="unique_fechamento_usuario_competencia",
            )
        ]

    def __str__(self):
        comp = self.competencia.strftime("%m/%Y") if isinstance(self.competencia, date) else str(self.competencia)
        status = "Fechado" if self.fechado else "Em aberto"
        return f"{self.usuario} - {comp} ({status})"


class AgendaEvento(models.Model):
    TIPO_CHOICES = [
        ('plantao', 'Plantão'),
        ('home_office', 'Home Office'),
        ('ferias', 'Férias'),
        ('folga_compensada', 'Folga Compensada')
    ]
    funcionario = models.ForeignKey(User, on_delete=models.CASCADE)
    data = models.DateField()
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    observacao = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ('funcionario', 'data')
