import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Q, Avg
from django.contrib.auth.models import User
from django.apps import apps

# Imports Union Desk
from clientes_sistemas.models import Cliente
from atendimentos_chamados.models import Atendimento
from sistemas.models import Sistema

@login_required
def central_home(request):
    hoje = timezone.now()
    inicio_mes = hoje.replace(day=1, hour=0, minute=0, second=0)

    # EFICIÊNCIA OPERACIONAL (TÉCNICOS)
    atendimentos_tecnico = User.objects.annotate(
        total_abertos=Count('atendimento', filter=Q(atendimento__status__in=['ABERTO', 'EM_ATENDIMENTO'])),
        total_concluido=Count('atendimento', filter=Q(atendimento__status='CONCLUIDO', atendimento__data_conclusao__gte=inicio_mes))
    ).filter(is_active=True).exclude(total_abertos=0, total_concluido=0).order_by('-total_concluido')

    # SLA E SAÚDE GLOBAL
    tickets_mes = Atendimento.objects.filter(data_conclusao__gte=inicio_mes)
    total_concluidos = tickets_mes.count()
    no_prazo = tickets_mes.filter(resolvido_no_prazo=True).count()
    sla_global = (no_prazo / total_concluidos * 100) if total_concluidos > 0 else 100

    # MARKET SHARE E TIER
    sistemas_stats = Sistema.objects.annotate(total=Count('clientes')).order_by('-total')
    
    context = {
        'atendimentos_tecnico': atendimentos_tecnico,
        'sla_global': round(sla_global, 1),
        'saude_media': Cliente.objects.filter(ativo=True).aggregate(Avg('health_score'))['health_score__avg'] or 0,
        'clientes_tier': {
            'A': Cliente.objects.filter(faturamento_cliente='A', ativo=True).count(),
            'B': Cliente.objects.filter(faturamento_cliente='B', ativo=True).count(),
            'outros': Cliente.objects.filter(ativo=True).exclude(faturamento_cliente__in=['A', 'B']).count(),
        },
        'radar_risco': Cliente.objects.filter(ativo=True).order_by('health_score')[:6],
        'sistemas_stats': sistemas_stats,
        'contagem': {
            'saudaveis': Cliente.objects.filter(nivel_risco='BAIXO').count(),
            'criticos': Cliente.objects.filter(nivel_risco='CRITICO').count(),
        }
    }
    return render(request, 'central_relatorios/index.html', context)