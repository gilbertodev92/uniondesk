# calendario_agenda/views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.http import Http404
from django.utils.dateparse import parse_datetime

from .models import CalendarEvent, EventConfirmation
from .forms import EventForm

# === GATILHO DA GAMIFICAÇÃO (IMPORTADO DO NOSSO CÉREBRO) ===
from recompensas.utils import processar_acao_gamificada


@login_required
def calendar_home(request):
    today = timezone.localdate()
    start_of_week = today - timezone.timedelta(days=today.weekday())
    end_of_week = start_of_week + timezone.timedelta(days=6)

    events = (
        CalendarEvent.objects
        .select_related("created_by")
        .prefetch_related("attendees")
        .order_by("start")
    )

    # =========================
    # MÉTRICAS REAIS
    # =========================

    eventos_hoje = events.filter(start__date=today).count()

    eventos_semana = events.filter(
        start__date__range=(start_of_week, end_of_week)
    ).count()

    implantacoes_semana = events.filter(
        source="implantacao",
        start__date__range=(start_of_week, end_of_week)
    ).count()

    treinamentos_semana = events.filter(
        source="cs",
        start__date__range=(start_of_week, end_of_week)
    ).count()

    # =========================
    # PAYLOAD FULLCALENDAR
    # =========================

    payload = []

    for ev in events:
        payload.append({
            "id": ev.id,
            "title": ev.title or "",
            "start": ev.start.isoformat(),
            "end": ev.end.isoformat() if ev.end else None,
            "allDay": bool(ev.all_day),
            "backgroundColor": ev.color if not ev.is_background else "#334155",
            "borderColor": ev.color,
            "textColor": "#0f172a",
            "extendedProps": {
                "empresa": ev.empresa_nome or "",
                "location": ev.location or "",
                "createdBy": ev.created_by.username if ev.created_by_id else "",
                "source": ev.source,
            },
            "url": reverse("calendario_agenda:event_edit", args=[ev.id]),
        })

    return render(
        request,
        "calendario_agenda/calendar.html",
        {
            "events_payload": payload,
            "metricas": {
                "hoje": eventos_hoje,
                "semana": eventos_semana,
                "implantacoes": implantacoes_semana,
                "treinamentos": treinamentos_semana,
            }
        }
    )

# ============================
# CRIAR NOVO EVENTO
# ============================
@login_required
def event_create(request):
    form = EventForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        ev = form.save(commit=False)
        ev.created_by = request.user
        ev.save()
        form.save_m2m()
        messages.success(request, "Evento criado com sucesso.")
        
        # ---> GAMIFICAÇÃO: Técnico agendou um compromisso/treinamento
        processar_acao_gamificada(
            usuario=request.user, 
            acao='criar_evento_agenda', 
            detalhe=f"Agenda: {ev.title[:30]}"
        )

        return redirect("calendario_agenda:calendar")

    return render(
        request,
        "calendario_agenda/event_form.html",
        {"form": form, "mode": "create"}
    )


@login_required
def event_edit(request, pk):
    ev = get_object_or_404(CalendarEvent, pk=pk)
    form = EventForm(request.POST or None, instance=ev)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Evento atualizado.")
        return redirect("calendario_agenda:calendar")

    return render(
        request,
        "calendario_agenda/event_form.html",
        {"form": form, "mode": "edit", "obj": ev}
    )


@login_required
def event_delete(request, pk):
    ev = get_object_or_404(CalendarEvent, pk=pk)

    if request.method != "POST":
        raise Http404()

    ev.delete()
    messages.success(request, "Evento excluído.")
    return redirect("calendario_agenda:calendar")


def confirm_attendance(request, token, decision):
    conf = get_object_or_404(EventConfirmation, token=token)

    if conf.status == "pending":
        if decision == "confirmar":
            conf.status = "confirmed"
        elif decision == "recusar":
            conf.status = "declined"

        conf.responded_at = timezone.now()
        conf.save(update_fields=["status", "responded_at"])

    return render(
        request,
        "calendario_agenda/confirm_success.html",
        {"conf": conf}
    )


@login_required
@require_POST
def atualizar_data_evento(request, pk):
    try:
        data = json.loads(request.body)
        evento = CalendarEvent.objects.get(pk=pk)
        
        # Pega as novas datas enviadas pelo calendário JavaScript
        novo_inicio = data.get('start')
        novo_fim = data.get('end')
        
        if novo_inicio:
            evento.start = parse_datetime(novo_inicio)
        if novo_fim:
            evento.end = parse_datetime(novo_fim)
        else:
            # Se for arrastado para um único dia sem hora de fim
            evento.end = evento.start
            
        evento.save()
        return JsonResponse({"status": "sucesso"})
        
    except CalendarEvent.DoesNotExist:
        return JsonResponse({"status": "erro", "mensagem": "Evento não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"status": "erro", "mensagem": str(e)}, status=400)