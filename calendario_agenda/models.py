from django.db import models
from django.conf import settings
import uuid
# Importação do módulo de clientes
from clientes_sistemas.models import Cliente 

class EventSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    CHAMADO = "chamado", "Atendimentos/Chamados"
    IMPLANTACAO = "implantacao", "Gestão de Implantação"
    CS = "cs", "CS - Satisfação"


class CalendarEvent(models.Model):
    # Básico
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    location = models.CharField(max_length=200, blank=True)

    contato_whatsapp = models.CharField(
        "Contato WhatsApp",
        max_length=20,
        blank=True,
        null=True,
        help_text="Formato: 55DDDNUMERO (apenas dígitos; aceita espaços/+, será normalizado)"
    )

    # Autor
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="events_created",
    )

    # Participantes (through explícito)
    attendees = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="EventAttendee",
        related_name="events_invited",
        blank=True,
    )

    # Origem/integrações
    source = models.CharField(
        max_length=20, choices=EventSource.choices, default=EventSource.MANUAL
    )
    source_object_id = models.CharField(max_length=64, blank=True)
    source_label = models.CharField(max_length=120, blank=True)

    # ===== INTEGRAÇÃO COM CLIENTE (NOVO) =====
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos_agenda',
        verbose_name="Cliente Vinculado"
    )
    
    # Mantemos este campo para eventos avulsos (não clientes)
    empresa_nome = models.CharField(max_length=160, blank=True, verbose_name="Empresa (Texto Livre)")

    # Visual
    color = models.CharField(max_length=9, default="#2563eb")
    icon_emoji = models.CharField(max_length=4, blank=True)  # ex.: "🎉"
    avatar_url = models.URLField(blank=True)
    style_variant = models.CharField(
        max_length=16,
        choices=[
            ("sticky", "Post-it"),
            ("label", "Etiqueta"),
            ("milestone", "Marco"),
            ("progress", "Progresso"),
        ],
        default="sticky",
    )
    progress_pct = models.PositiveSmallIntegerField(null=True, blank=True)  # 0–100
    is_background = models.BooleanField(default=False)

    # Lembrete
    remind_minutes_before = models.PositiveSmallIntegerField(
        default=30,
        help_text="Minutos antes do início para enviar lembrete.",
    )
    reminded_at = models.DateTimeField(null=True, blank=True)

    # Auditoria
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start"]
        indexes = [
            models.Index(fields=["start"]),
            models.Index(fields=["end"]),
            models.Index(fields=["source"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.start} → {self.end})"


class EventAttendee(models.Model):
    event = models.ForeignKey(
        CalendarEvent, on_delete=models.CASCADE, related_name="attendee_links"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calendar_links"
    )

    class Meta:
        unique_together = ("event", "user")
        verbose_name = "Participante de Evento"
        verbose_name_plural = "Participantes de Evento"

    def __str__(self) -> str:
        return f"{self.user} @ {self.event}"


class ReminderLog(models.Model):
    CHANNEL_CHOICES = (("email", "E-mail"), ("whatsapp", "WhatsApp"))
    KIND_CHOICES = (("reminder", "Lembrete"), ("confirmation", "Confirmação"))

    event = models.ForeignKey(
        "CalendarEvent", on_delete=models.CASCADE, related_name="reminder_logs"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_reminders"
    )
    channel = models.CharField(max_length=16, choices=CHANNEL_CHOICES, default="email")
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="reminder")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user", "channel", "kind")

    def __str__(self) -> str:
        return f"{self.event_id} | {self.user_id} | {self.channel}"


class EventConfirmation(models.Model):
    STATUS = (
        ("pending", "Pendente"),
        ("confirmed", "Confirmado"),
        ("declined", "Recusado"),
    )

    event = models.ForeignKey(
        CalendarEvent, on_delete=models.CASCADE, related_name="confirmations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_confirmations"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_id} | {self.user_id} | {self.status}"
    
    # Adicione isso no FINAL do seu arquivo calendario_agenda/models.py

from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .tasks import notify_new_attendee_whatsapp

@receiver(m2m_changed, sender=CalendarEvent.attendees.through)
def trigger_whatsapp_on_new_attendee(sender, instance, action, pk_set, **kwargs):
    """
    Escuta mudanças no campo ManyToMany 'attendees'.
    Se um novo técnico for adicionado (post_add), dispara a notificação do WhatsApp.
    """
    # Apenas age DEPOIS que a relação foi salva no banco e apenas para usuários NOVOS no evento
    if action == "post_add" and pk_set:
        for user_id in pk_set:
            # Dispara a task de forma assíncrona (não trava a tela de quem está salvando o evento)
            notify_new_attendee_whatsapp.delay(instance.id, user_id)