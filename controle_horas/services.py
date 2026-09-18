# /home/logica/projetos/union/union_desk/apps/controle_horas/services.py
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Sum
from .models import Apontamento, FechamentoMensal, ConfigHoras

def consolidar_fechamento(usuario, competencia_date, fechar=False, gestor=None):
    """
    competencia_date: datetime.date (usar dia 1 do mês)
    """
    # intervalo do mês
    first = competencia_date.replace(day=1)
    if first.month == 12:
        last = first.replace(year=first.year+1, month=1, day=1) - timedelta(days=1)
    else:
        last = first.replace(month=first.month+1, day=1) - timedelta(days=1)

    qs = Apontamento.objects.filter(
        usuario=usuario, data__gte=first, data__lte=last, status='aprovado'
    )

    tot = qs.aggregate(
        min_total=Sum('minutos_total'),
        min_extra=Sum('minutos_extra')
    )

    min_total = tot['min_total'] or 0
    min_extra = tot['min_extra'] or 0

    # alvo mensal (jornada diária * dias úteis com apontamento)
    cfg = ConfigHoras.objects.filter(ativo=True).first()
    alvo_dia = int((cfg.horas_dia if cfg else 8.0) * 60)

    # Conta dias com apontamento aprovado para referência
    dias = qs.values_list('data', flat=True).distinct().count()
    alvo_mes = alvo_dia * dias

    saldo = min_total - alvo_mes

    fech, _ = FechamentoMensal.objects.get_or_create(usuario=usuario, competencia=first)
    fech.minutos_trabalhados = min_total
    fech.minutos_extras = min_extra
    fech.saldo_banco = saldo

    if fechar:
        fech.status = 'fechado'
        fech.fechado_por = gestor
        fech.fechado_em = timezone.now()

    fech.save()
    return fech
