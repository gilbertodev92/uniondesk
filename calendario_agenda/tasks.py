# calendario_agenda/tasks.py
from __future__ import annotations

import json
import logging
import re
from datetime import timedelta
from typing import Iterable, Tuple, Optional

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail, BadHeaderError
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from .models import CalendarEvent, ReminderLog

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURAÇÃO WHATSAPP (Evolution API)
# ============================================================
EVOLUTION_API_URL = getattr(settings, "EVOLUTION_API_URL", "http://127.0.0.1:8080").rstrip("/")
EVOLUTION_API_KEY = getattr(settings, "EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE = getattr(settings, "EVOLUTION_INSTANCE", "atendimento_suporte")

# ============================================================
# CLIENTE EVOLUTION (envia WhatsApp)
# ============================================================
class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, instance: str):
        self.base = (base_url or "").rstrip("/")
        self.key = api_key or ""
        self.instance = instance or ""
        self.headers = {
            "Content-Type": "application/json",
            "apikey": self.key,
        }

    @staticmethod
    def normalize_br_number(number: str) -> str:
        digits = re.sub(r"\D+", "", number or "")
        if not digits:
            return ""
        if digits.startswith("55"):
            return digits
        digits = digits.lstrip("0")
        if len(digits) in (10, 11):
            return f"55{digits}"
        return digits

    def send_text(self, number: str, text: str) -> bool:
        number = self.normalize_br_number(number)
        if not number:
            raise ValueError("Número inválido para WhatsApp.")
        url = f"{self.base}/message/sendText/{self.instance}"
        payload = {"number": number, "text": text}
        resp = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=30)
        if resp.status_code >= 400:
            logger.error("Evolution API error %s: %s", resp.status_code, resp.text)
            return False
        try:
            data = resp.json()
        except Exception:
            logger.error("Evolution API retornou não-JSON: %s", resp.text[:200])
            return False
        ok = str(data.get("status", "")).lower() in ("success", "ok", "true","pending")
        if not ok:
            logger.error("Falha no envio (payload=%s resp=%s)", payload, data)
        return ok


def get_whatsapp_client() -> EvolutionClient:
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not EVOLUTION_INSTANCE:
        raise RuntimeError(
            "Configuração WhatsApp ausente. Defina EVOLUTION_API_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE no settings/.env."
        )
    return EvolutionClient(EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE)

# ============================================================
# UTILITÁRIOS
# ============================================================
def _human_dt(dt):
    local = timezone.localtime(dt)
    return local.strftime("%d/%m/%Y %H:%M")

def _build_email(ev: CalendarEvent) -> Tuple[str, str]:
    subject = f"[Lembrete] {ev.title} às {_human_dt(ev.start)}"
    lines = [
        "Olá,",
        "",
        f"Lembrete do evento: {ev.title}",
        f"Início: {_human_dt(ev.start)}",
        f"Término: {_human_dt(ev.end)}",
    ]
    if getattr(ev, "empresa_nome", None):
        lines.append(f"Empresa: {ev.empresa_nome}")
    if getattr(ev, "location", None):
        lines.append(f"Local: {ev.location}")
    if getattr(ev, "description", None):
        lines.extend(["", "Descrição:", ev.description])
    return subject, "\n".join(lines)

def _build_whatsapp_text(ev: CalendarEvent) -> str:
    parts = [
        "🔔 *Lembrete de evento*",
        f"*Título:* {ev.title}",
        f"*Início:* {_human_dt(ev.start)}",
        f"*Término:* {_human_dt(ev.end)}",
    ]
    if getattr(ev, "empresa_nome", None):
        parts.append(f"*Empresa:* {ev.empresa_nome}")
    if getattr(ev, "location", None):
        parts.append(f"*Local:* {ev.location}")
    if getattr(ev, "description", None):
        parts.extend(["", ev.description])
    return "\n".join(parts)

def _iter_recipients_email(ev: CalendarEvent) -> Iterable[Tuple[object, str]]:
    seen = set()
    if ev.created_by and getattr(ev.created_by, "email", None):
        email = (ev.created_by.email or "").strip()
        if email and email not in seen:
            seen.add(email)
            yield ev.created_by, email
    for u in ev.attendees.all():
        email = (getattr(u, "email", "") or "").strip()
        if email and email not in seen:
            seen.add(email)
            yield u, email

# --------------------- BUSCA DE TELEFONE ---------------------
PHONE_ATTRS = ("whatsapp", "phone", "telefone", "celular", "mobile")

NESTED_PHONE_PATHS = (
    "profile.whatsapp",
    "profile.phone",
    "profile.telefone",
    "profile.celular",
    "profile.phone_e164",  # <-- ADICIONADO (confirmado no seu modelo)
    "dados.whatsapp",
    "contato.whatsapp",
    "userprofile.whatsapp",
    "employee.whatsapp",
)

OPTIN_ATTRS = ("aceita_lembretes_whatsapp", "whatsapp_optin", "aceita_whatsapp", "allow_whatsapp")

def _dig(obj, path: str) -> Optional[str]:
    cur = obj
    for part in path.split("."):
        cur = getattr(cur, part, None)
        if cur is None:
            return None
    if isinstance(cur, str):
        return cur.strip()
    return str(cur).strip() if cur is not None else None

def _has_optin(user) -> bool:
    for attr in OPTIN_ATTRS:
        val = getattr(user, attr, None)
        if val is False:
            return False
        if val is True:
            return True
    return True

def _get_phone(user) -> Optional[str]:
    if not _has_optin(user):
        return None

    for attr in PHONE_ATTRS:
        val = getattr(user, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()

    for path in NESTED_PHONE_PATHS:
        val = _dig(user, path)
        if val:
            return val

    return None

def _normalize_msisdn(raw: str) -> Optional[str]:
    digits = re.sub(r"\D+", "", raw or "")
    if not digits:
        return None
    if digits.startswith("55"):
        return digits
    if len(digits) in (10, 11):
        return "55" + digits
    return digits

def _iter_recipients_whatsapp(ev: CalendarEvent) -> Iterable[Tuple[object, str]]:
    seen = set()
    if ev.created_by:
        p = _get_phone(ev.created_by)
        p = _normalize_msisdn(p) if p else None
        if p and p not in seen:
            seen.add(p)
            yield ev.created_by, p
    for u in ev.attendees.all():
        p = _get_phone(u)
        p = _normalize_msisdn(p) if p else None
        if p and p not in seen:
            seen.add(p)
            yield u, p

def _should_fire(now, ev: CalendarEvent) -> bool:
    minutes = (ev.remind_minutes_before or 0)
    if minutes <= 0:
        return False
    trigger = ev.start - timedelta(minutes=minutes)
    return trigger <= now < (trigger + timedelta(minutes=1))

# ============================================================
# TASKS
# ============================================================
@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=60, retry_kwargs={"max_retries": 3})
def send_event_email_reminders(self):
    now = timezone.now()
    horizon = now + timedelta(hours=2)
    qs = (
        CalendarEvent.objects
        .filter(start__gte=now - timedelta(hours=1), start__lte=horizon)
        .select_related("created_by")
        .prefetch_related(Prefetch("attendees"))
        .order_by("start")
    )

    total_events = total_scheduled = total_skipped = 0

    for ev in qs:
        total_events += 1
        if not _should_fire(now, ev):
            total_skipped += 1
            continue

        subject, body = _build_email(ev)
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@localhost"

        for user, email in _iter_recipients_email(ev):
            try:
                with transaction.atomic():
                    log, created = ReminderLog.objects.get_or_create(
                        event=ev, user=user, channel="email", kind="reminder"
                    )
                    if not created:
                        continue
            except Exception as e:
                logger.warning("Race ao criar ReminderLog (event=%s user=%s): %s", ev.id, getattr(user, "id", None), e)
                continue

            try:
                send_mail(subject, body, from_email, [email], fail_silently=False)
                total_scheduled += 1
                logger.info("E-mail enviado (event=%s -> %s)", ev.id, email)
            except BadHeaderError as bhe:
                logger.error("BadHeaderError (event=%s): %s", ev.id, bhe)
            except Exception as ex:
                logger.exception("Falha ao enviar e-mail (event=%s -> %s), retry: %s", ev.id, email, ex)
                raise

    logger.info("Lembretes (e-mail): eventos=%s, enviados=%s, ignorados=%s",
                total_events, total_scheduled, total_skipped)
    return {"events": total_events, "sent": total_scheduled, "skipped": total_skipped}

# ============================================================
# TASK WHATSAPP
# ============================================================
@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=60, retry_kwargs={"max_retries": 3})
def send_event_whatsapp_reminders(self):
    now = timezone.now()
    horizon = now + timedelta(hours=2)

    try:
        client = get_whatsapp_client()
    except Exception as e:
        logger.error("WhatsApp client error: %s", e)
        return {"events": 0, "sent": 0, "skipped": 0}

    qs = (
        CalendarEvent.objects
        .filter(start__gte=now - timedelta(hours=1), start__lte=horizon)
        .select_related("created_by")
        .prefetch_related(Prefetch("attendees"))
        .order_by("start")
    )

    total_events = total_sent = total_skipped = 0

    for ev in qs:
        total_events += 1
        if not _should_fire(now, ev):
            total_skipped += 1
            continue

        text = _build_whatsapp_text(ev)

        for user, number in _iter_recipients_whatsapp(ev):
            try:
                with transaction.atomic():
                    log, created = ReminderLog.objects.get_or_create(
                        event=ev, user=user, channel="whatsapp", kind="reminder"
                    )
                    if not created:
                        continue
            except Exception as e:
                logger.warning("Race ao criar ReminderLog(WA) (event=%s user=%s): %s", ev.id, getattr(user, "id", None), e)
                continue

            ok = False
            try:
                ok = client.send_text(number, text)
            except Exception as ex:
                logger.exception("Erro Evolution API (event=%s -> %s): %s", ev.id, number, ex)

            if ok:
                total_sent += 1
                logger.info("WhatsApp enviado (event=%s -> %s)", ev.id, number)
            else:
                logger.error("WhatsApp falhou (event=%s -> %s)", ev.id, number)

    logger.info("Lembretes (whatsapp): eventos=%s, enviados=%s, ignorados=%s",
                total_events, total_sent, total_skipped)
    return {"events": total_events, "sent": total_sent, "skipped": total_skipped}

# ============================================================
# TESTES / DEBUG
# ============================================================
@shared_task
def send_test_email():
    subject = "🔔 Teste de lembrete - Union Desk"
    message = (
        "Este é um e-mail de teste do sistema de lembretes.\n\n"
        "Se você está vendo isso no terminal (backend console), está tudo certo!"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@localhost"
    to = [getattr(settings, "ADMINS_EMAIL_FOR_TESTS", None) or "teste@union.local"]
    try:
        send_mail(subject, message, from_email, to, fail_silently=False)
        logger.info("E-mail de teste enviado para: %s", to)
        return True
    except Exception:
        logger.exception("Erro ao enviar e-mail de teste")
        return False

@shared_task
def send_test_whatsapp_real():
    number = (getattr(settings, "WHATSAPP_TEST_NUMBER", "") or "").strip()
    if not number:
        logger.error("Defina WHATSAPP_TEST_NUMBER no settings/.env para testar.")
        return False
    try:
        client = get_whatsapp_client()
    except Exception as e:
        logger.error("WhatsApp client error: %s", e)
        return False
    msg = "🔔 Teste de WhatsApp do Union Desk – tudo certo!"
    try:
        ok = client.send_text(number, msg)
        logger.info("Teste WhatsApp para %s -> %s", number, ok)
        return bool(ok)
    except Exception:
        logger.exception("Erro no envio de teste WhatsApp")
        return False

@shared_task
def ping():
    logger.info("pong")
    return "pong"

# Adicione isso no FINAL do seu arquivo calendario_agenda/tasks.py

@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=60, retry_kwargs={"max_retries": 3})
def notify_new_attendee_whatsapp(self, event_id: int, user_id: int):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        ev = CalendarEvent.objects.get(pk=event_id)
        tecnico = User.objects.get(pk=user_id)
    except (CalendarEvent.DoesNotExist, User.DoesNotExist):
        logger.warning(f"Evento {event_id} ou Usuário {user_id} deletado antes do envio.")
        return "Cancelado"

    # Usa a sua lógica super robusta para achar o telefone correto do usuário
    raw_phone = _get_phone(tecnico)
    phone = _normalize_msisdn(raw_phone) if raw_phone else None

    if not phone:
        logger.info(f"Usuário {tecnico.username} não possui telefone válido para notificação.")
        return "Sem telefone"

    try:
        client = get_whatsapp_client()
    except Exception as e:
        logger.error("Erro ao carregar client WhatsApp na atribuição: %s", e)
        return "Erro Client WA"

    # Monta a mensagem aproveitando seu _human_dt
    data_str = _human_dt(ev.start)
    msg = (
        f"⚠️ *Novo Evento Atribuído!*\n\n"
        f"Olá {tecnico.first_name or tecnico.username},\n"
        f"Você foi alocado em um evento no Union Desk.\n\n"
        f"📌 *Título:* {ev.title}\n"
        f"📅 *Início:* {data_str}\n"
    )
    
    if getattr(ev, "empresa_nome", None):
        msg += f"🏢 *Empresa:* {ev.empresa_nome}\n"
        
    msg += "\nAcesse seu calendário para mais detalhes."

    # Dispara a mensagem
    ok = client.send_text(phone, msg)
    if ok:
        logger.info(f"Notificação de atribuição enviada para {tecnico.username} ({phone})")
    else:
        logger.error(f"Falha ao notificar atribuição para {tecnico.username} ({phone})")
        
    return "Enviado" if ok else "Falha"


# Adicione isso no final do seu calendario_agenda/tasks.py

@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=60, retry_kwargs={"max_retries": 3})
def notify_tecnico_novo_atendimento(self, atendimento_id: int):
    # Precisamos importar o modelo aqui dentro para evitar importação circular
    from atendimentos_chamados.models import Atendimento
    
    try:
        atendimento = Atendimento.objects.select_related("tecnico_responsavel", "cliente").get(pk=atendimento_id)
        tecnico = atendimento.tecnico_responsavel
    except Atendimento.DoesNotExist:
        logger.warning(f"Atendimento {atendimento_id} não encontrado para notificação.")
        return "Cancelado"

    if not tecnico:
        return "Sem técnico"

    # Usa as suas lógicas perfeitas de caçar o telefone
    raw_phone = _get_phone(tecnico)
    phone = _normalize_msisdn(raw_phone) if raw_phone else None

    if not phone:
        logger.info(f"Usuário {tecnico.username} não possui telefone configurado.")
        return "Sem telefone"

    try:
        client = get_whatsapp_client()
    except Exception as e:
        logger.error("Erro ao carregar client WhatsApp para Atendimentos: %s", e)
        return "Erro Client WA"

    # Monta a mensagem de "Chamado/OS"
    prioridade_emoji = {
        "CRITICA": "🚨",
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAIXA": "🟢"
    }.get(atendimento.prioridade, "🔵")

    msg = (
        f"{prioridade_emoji} *Novo Chamado Atribuído!*\n\n"
        f"Olá {tecnico.first_name or tecnico.username},\n"
        f"Um chamado no Union Desk foi transferido para você.\n\n"
        f"📌 *Chamado: #{atendimento.numero}*\n"
        f"👤 *Cliente:* {atendimento.cliente.razao_social}\n"
        f"⚠️ *Prioridade:* {atendimento.get_prioridade_display()}\n\n"
        f"Acesse o painel para mais detalhes."
    )

    # Dispara a mensagem
    ok = client.send_text(phone, msg)
    if ok:
        logger.info(f"Notificação de Chamado #{atendimento.numero} enviada para {tecnico.username}")
    else:
        logger.error(f"Falha ao notificar Chamado #{atendimento.numero} para {tecnico.username}")
        
    return "Enviado" if ok else "Falha"


    # ============================================================
# NOTIFICAÇÃO BROADCAST (FILA/SETOR INTEIRO)
# ============================================================
@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=60, retry_kwargs={"max_retries": 3})
def notify_setor_novo_atendimento(self, atendimento_id: int):
    from atendimentos_chamados.models import Atendimento
    from django.contrib.auth.models import Group
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        atendimento = Atendimento.objects.select_related("setor_atual", "cliente").get(pk=atendimento_id)
    except Atendimento.DoesNotExist:
        logger.warning(f"[BROADCAST] Atendimento {atendimento_id} não encontrado.")
        return "Cancelado"

    setor = atendimento.setor_atual
    if not setor:
        return "Sem Setor"

    # Busca o Grupo do Django que tem o mesmo nome do Setor (Ignora maiúsculo/minúsculo)
    try:
        grupo = Group.objects.get(name__iexact=setor.nome)
        usuarios_fila = grupo.user_set.filter(is_active=True)
    except Group.DoesNotExist:
        logger.warning(f"[BROADCAST] Grupo de permissão '{setor.nome}' não existe no Django Admin.")
        return "Sem Grupo"

    if not usuarios_fila.exists():
        logger.info(f"[BROADCAST] A fila '{setor.nome}' não tem nenhum usuário ativo.")
        return "Fila Vazia"

    try:
        client = get_whatsapp_client()
    except Exception as e:
        logger.error("[BROADCAST] Erro ao carregar client WhatsApp: %s", e)
        return "Erro Client WA"

    # Monta a mensagem que todo mundo vai receber
    prioridade_emoji = {
        "CRITICA": "🚨🚨🚨",
        "ALTA": "🔴",
        "MEDIA": "🟡",
        "BAIXA": "🟢"
    }.get(atendimento.prioridade, "🔵")

    base_msg = (
        f"{prioridade_emoji} *NOVO CHAMADO NA FILA: {setor.nome.upper()}* {prioridade_emoji}\n\n"
        f"Atenção equipe! Um novo atendimento foi direcionado para a fila e está aguardando um responsável.\n\n"
        f"📌 *Chamado:* #{atendimento.numero}\n"
        f"👤 *Cliente:* {atendimento.cliente.razao_social}\n"
        f"⚠️ *Prioridade:* {atendimento.get_prioridade_display()}\n\n"
        f"Quem estiver livre, por favor, puxe o atendimento no painel! 🚀"
    )

    enviados = 0
    falhas = 0

    # Faz o loop e atira a mensagem no WhatsApp de cada um do setor
    for usuario in usuarios_fila:
        raw_phone = _get_phone(usuario)
        phone = _normalize_msisdn(raw_phone) if raw_phone else None

        if not phone:
            logger.info(f"[BROADCAST] Ignorando {usuario.username}: Sem telefone.")
            continue

        ok = client.send_text(phone, base_msg)
        if ok:
            enviados += 1
        else:
            falhas += 1
            logger.error(f"[BROADCAST] Falha ao enviar para {usuario.username} ({phone})")

    resultado = f"Enviados: {enviados}, Falhas: {falhas}"
    logger.info(f"[BROADCAST] Resumo OS #{atendimento.numero} para {setor.nome}: {resultado}")
    return resultado