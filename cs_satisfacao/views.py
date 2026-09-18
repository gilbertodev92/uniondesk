import json
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Prefetch, Q, Count
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from clientes_sistemas.models import Cliente
from atendimentos_chamados.models import Atendimento
from calendario_agenda.models import CalendarEvent  
from .models import EventoCS, CancelamentoCliente # IMPORT DO CANCELAMENTO AQUI!
from .forms import EventoCSForm
from recompensas.utils import processar_acao_gamificada


# ==============================================================================
# HELPER: gera um Lead de upsell no CRM a partir de um evento de CS.
# Antes esta lógica estava DUPLICADA em adicionar_evento_cliente e criar_cs.
# Centralizar evita que as duas cópias divirjam com o tempo.
# ==============================================================================
def _gerar_oportunidade_upsell(cliente, usuario, observacoes):
    from crm_vendas.models import Lead, AnotacaoLead

    nome_cs = (usuario.get_full_name() or usuario.username) if (usuario and usuario.is_authenticated) else "Sistema"
    texto_obs = f"🚀 OPORTUNIDADE E UPSELL INDICADO PELO CS: {nome_cs.upper()}\n\nDetalhes do Contato: {observacoes or ''}"
    responsavel = usuario if (usuario and usuario.is_authenticated) else None

    novo_lead = Lead.objects.create(
        nome_empresa=cliente.razao_social,
        nome_contato=cliente.nome_responsavel or "Aos cuidados da Gestão",
        telefone=cliente.telefone_responsavel or cliente.telefone or "Não informado",
        cidade=cliente.cidade or "Não informada",
        cnpj=cliente.cnpj,
        origem='INDICACAO_CLIENTE',
        etapa='1_LEAD',
        urgencia='ALTA',
        cliente_existente=cliente,
        vendedor_prospeccao=responsavel,
        observacao_rapida=texto_obs,
        necessidade_desejo=texto_obs,
    )
    AnotacaoLead.objects.create(
        lead=novo_lead,
        vendedor=responsavel,
        texto=texto_obs,
        etapa_no_momento='1_LEAD',
    )
    return novo_lead


# ==============================================================================
# PAINEL PRINCIPAL (CS)
# ==============================================================================
# ==============================================================================
# PAINEL PRINCIPAL (CS) - NÍVEL NASA (WORKSPACE)
# ==============================================================================
# ==============================================================================
# PAINEL PRINCIPAL (CS) - NÍVEL NASA (WORKSPACE + MÉTRICAS)
# ==============================================================================
@login_required
def painel_cs(request):
    busca = request.GET.get("busca", "").strip()
    clientes_qs = Cliente.objects.filter(ativo=True)

    if busca:
        clientes_qs = clientes_qs.filter(
            Q(razao_social__icontains=busca) | Q(cnpj__icontains=busca)
        )

    clientes = clientes_qs.prefetch_related(
        Prefetch("eventos_cs", queryset=EventoCS.objects.all())
    )

    dados = []
    hoje = timezone.now().date()
    trinta_dias_atras = hoje - timezone.timedelta(days=30)
    
    # 🔥 AJUSTE CIRÚRGICO: Fixamos a data de corte para HOJE (29/04/2026).
    # O sistema vai ignorar a massa de dados importada e a tela vai carregar voando!
    from datetime import date
    limite_onboarding = date(2026, 4, 29)

    # 1. PROCESSAMENTO BASE
    for cliente in clientes:
        eventos = list(cliente.eventos_cs.all())  # usa o cache do prefetch_related

        realizados_com_data = [
            e for e in eventos
            if e.status == 'REALIZADO' and e.data_realizada
        ]
        ultimo_realizado = (
            max(realizados_com_data, key=lambda e: e.data_realizada)
            if realizados_com_data else None
        )

        eventos_vencidos = sum(
            1 for e in eventos
            if e.status == 'PENDENTE' and e.data_prevista and e.data_prevista < hoje
        )

        dias = (hoje - ultimo_realizado.data_realizada).days if ultimo_realizado else 999

        dados.append({
            "cliente": cliente,
            "score": cliente.health_score,
            "nivel": cliente.get_nivel_risco_display(),
            "dias": dias,
            "vencidos": eventos_vencidos,
        })

    dados.sort(key=lambda x: x["score"])

  # 2. INTELIGÊNCIA DA MESA DE TRABALHO
    clientes_uti = [d for d in dados if d['score'] < 70]
    
    tarefas_pendentes = EventoCS.objects.filter(
        status='PENDENTE', data_prevista__lte=hoje
    ).select_related('cliente').order_by('data_prevista')

    score_medio = sum(d["score"] for d in dados) / len(dados) if dados else 0

    # =========================================================
    # 3. INTELIGÊNCIA DE MÉTRICAS E CHURN (Últimos 30 dias)
    # =========================================================
    
    # Cancelamentos (Churn)
    cancelamentos_recentes = CancelamentoCliente.objects.filter(
        data_cancelamento__gte=trinta_dias_atras
    ).order_by('-data_cancelamento')
    total_cancelamentos = cancelamentos_recentes.count()

    # Dores / Atritos relatados
    eventos_com_dor = EventoCS.objects.filter(
        data_realizada__gte=trinta_dias_atras,
        status='REALIZADO'
    ).exclude(motivo_risco='NENHUM')

    dores = {
        'atendimento': eventos_com_dor.filter(motivo_risco='ATENDIMENTO').count(),
        'funcionalidade': eventos_com_dor.filter(motivo_risco='FUNCIONALIDADE').count(),
        'bugs': eventos_com_dor.filter(motivo_risco='BUGS').count(),
        'concorrencia': eventos_com_dor.filter(motivo_risco='CONCORRENCIA').count(),
        'financeiro': eventos_com_dor.filter(motivo_risco='FINANCEIRO').count(),
    }
    
    total_dores = sum(dores.values())
# =========================================================
    # 4. ABA DE UPSELLS E COMISSÕES (DADOS DO CRM)
    # =========================================================
    from crm_vendas.models import Lead
    
    # Pega todos os Leads gerados pelo CS
    oportunidades_geradas = Lead.objects.filter(
        origem='INDICACAO_CLIENTE'
    ).order_by('-data_criacao')
    
    # Calculando os ganhos pra cobrar o patrão!
    upsells_ganhos = oportunidades_geradas.filter(etapa='6_GANHO').count()
    upsells_em_aberto = oportunidades_geradas.exclude(etapa__in=['6_GANHO', '7_PERDIDO']).count()
    upsells_perdidos = oportunidades_geradas.filter(etapa='7_PERDIDO').count()

    # ==========================================================================
    # NOVOS GRÁFICOS CS: PRODUTIVIDADE, ATRASOS E CLIENTES ATENDIDOS
    # ==========================================================================
    cs_realizados_mes = EventoCS.objects.filter(status='REALIZADO', data_realizada__gte=trinta_dias_atras, data_realizada__lte=hoje)
    
    # 1. Eventos Realizados por Técnico
    cs_tec_stats = cs_realizados_mes.exclude(responsavel__isnull=True).values('responsavel__first_name', 'responsavel__username').annotate(total=Count('id')).order_by('-total')[:7]
    cs_labels_tec = [(t['responsavel__first_name'] or t['responsavel__username']).upper() for t in cs_tec_stats]
    cs_dados_tec = [t['total'] for t in cs_tec_stats]

    # 2. Eventos Atrasados por Técnico (Tarefas vencidas até ontem)
    cs_pend_tec_stats = EventoCS.objects.filter(status='PENDENTE', data_prevista__lt=hoje).exclude(responsavel__isnull=True).values('responsavel__first_name', 'responsavel__username').annotate(total=Count('id')).order_by('-total')[:7]
    cs_labels_pend_tec = [(t['responsavel__first_name'] or t['responsavel__username']).upper() for t in cs_pend_tec_stats]
    cs_dados_pend_tec = [t['total'] for t in cs_pend_tec_stats]

    # 3. Últimos Clientes Pesquisados/Atendidos no Mês
    clientes_cs_mes = []
    vistos = set()
    for ev in cs_realizados_mes.select_related('cliente', 'responsavel').order_by('-data_realizada'):
        if ev.cliente.pk not in vistos:
            vistos.add(ev.cliente.pk)
            nome_tec = ev.responsavel.first_name if ev.responsavel and ev.responsavel.first_name else (ev.responsavel.username if ev.responsavel else "Sistema")
            clientes_cs_mes.append({
                'nome': ev.cliente.razao_social,
                'data': ev.data_realizada.strftime('%d/%m'),
                'score': ev.cliente.health_score,
                'tec': nome_tec.upper()
            })
            if len(clientes_cs_mes) >= 15: break

    # 🔥 TRAVA DE PERFORMANCE DA BASE COMPLETA
    mostrar_todos = request.GET.get('todos') == '1'
    dados_base = dados if mostrar_todos else dados[:20]

    context = {
        "dados": dados,
        "dados_base": dados_base,
        "mostrar_todos": mostrar_todos,
        "score_medio": round(score_medio, 1),
        "clientes_uti": clientes_uti,
        "clientes_onboarding": [],
        "tarefas_pendentes": tarefas_pendentes,
        "hoje": hoje,
        "cancelamentos_recentes": cancelamentos_recentes,
        "total_cancelamentos": total_cancelamentos,
        "dores": dores,
        "total_dores": total_dores,
        "oportunidades_geradas": oportunidades_geradas,
        "upsells_ganhos": upsells_ganhos,
        "upsells_em_aberto": upsells_em_aberto,
        "upsells_perdidos": upsells_perdidos,
        "cs_labels_tec": json.dumps(cs_labels_tec),
        "cs_dados_tec": json.dumps(cs_dados_tec),
        "cs_labels_pend_tec": json.dumps(cs_labels_pend_tec),
        "cs_dados_pend_tec": json.dumps(cs_dados_pend_tec),
        "clientes_cs_mes": clientes_cs_mes,
    }
    return render(request, "cs_satisfacao/painel_cs.html", context)

# ==============================================================================
# DETALHES DO CLIENTE (UNIFICADO COM CALENDÁRIO)
# ==============================================================================
@login_required
def detalhe_cliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, pk=cliente_id)
    cliente.calcular_health_score()
    
    eventos_cs = cliente.eventos_cs.all().order_by('-data_prevista')
    eventos_calendario = CalendarEvent.objects.filter(cliente=cliente).order_by('-start')
    ultimos_tickets = Atendimento.objects.filter(cliente=cliente).order_by('-data_abertura')[:5]
    
    context = {
        'cliente': cliente,
        'eventos': eventos_cs,
        'eventos_calendario': eventos_calendario,
        'ultimos_tickets': ultimos_tickets,
        'hoje': timezone.now().date(),
    }
    return render(request, 'cs_satisfacao/detalhe_cliente.html', context)


# ==============================================================================
# ADICIONAR EVENTO RÁPIDO (MODAL)
# ==============================================================================
# ==============================================================================
# ADICIONAR EVENTO RÁPIDO (MODAL)
# ==============================================================================
@login_required
def adicionar_evento_cliente(request, cliente_id):
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=cliente_id)
        
        tipo_bd = request.POST.get('tipo_contato', 'FOLLOWUP')
        motivo_bd = request.POST.get('motivo_risco', 'NENHUM')
        status_bd = request.POST.get('status', 'REALIZADO')
        observacoes_cs = request.POST.get('observacoes', '')
        
        evento = EventoCS.objects.create(
            cliente=cliente,
            responsavel=request.user if request.user.is_authenticated else None,
            tipo_contato=tipo_bd,
            motivo_risco=motivo_bd,
            status=status_bd,
            data_prevista=request.POST.get('data_prevista', timezone.now().date()),
            observacoes=observacoes_cs
        )
        
        # ============================================================
        # 🚀 O GATILHO NÍVEL NASA: INTEGRAÇÃO COM CRM DE VENDAS
        # ============================================================
        gera_oportunidade = request.POST.get('gera_oportunidade') == 'on' or request.POST.get('gera_oportunidade') == 'True'

        if gera_oportunidade:
            _gerar_oportunidade_upsell(cliente, request.user, observacoes_cs)
            messages.success(request, "Contato registrado e Oportunidade Comercial enviada para o CRM!")
        else:
            messages.success(request, "Contato registrado! A saúde do cliente foi recalculada.")
            
        if request.user.is_authenticated:
            processar_acao_gamificada(
                usuario=request.user, 
                acao='registrar_contato_cs', 
                detalhe=f"CS Registrado: {cliente.razao_social[:20]}"
            )
        
    return redirect('cs_satisfacao:detalhe_cliente', cliente_id=cliente_id)
# ==============================================================================
# UTILS E APIS
# ==============================================================================
@login_required
def buscar_clientes(request):
    q = request.GET.get("q", "")
    clientes = Cliente.objects.filter(
        razao_social__icontains=q,
        ativo=True
    )[:10]

    data = [
        {"id": c.pk, "nome": c.razao_social, "cnpj": c.cnpj}
        for c in clientes
    ]
    return JsonResponse(data, safe=False)

@login_required
def criar_cs(request):
    if request.method == "POST":
        form = EventoCSForm(request.POST)
        if form.is_valid():
            evento = form.save()
            
            # 🔥 A MÁGICA DA INTEGRAÇÃO
            if evento.gera_oportunidade:
                _gerar_oportunidade_upsell(evento.cliente, request.user, evento.observacoes)
                messages.success(request, "Contato registrado e Oportunidade Comercial enviada para o CRM!")
            else:
                messages.success(request, "Acompanhamento criado com sucesso.")
            
            if request.user.is_authenticated:
                processar_acao_gamificada(
                    usuario=request.user, 
                    acao='registrar_contato_cs', 
                    detalhe=f"CS Registrado: {evento.cliente.razao_social[:20]}"
                )
            return redirect("cs_satisfacao:painel_cs")
        else:
            messages.error(request, "Verifique os campos do formulário.")
    else:
        form = EventoCSForm()
    return render(request, "cs_satisfacao/form_cs.html", {"form": form})

# ==============================================================================
# NOVA FUNÇÃO: REGISTRO DE CANCELAMENTO (CHURN)
# ==============================================================================
@login_required
def cancelar_cliente(request):
    if request.method == "POST":
        cliente_id = request.POST.get('cliente_id')
        motivo = request.POST.get('motivo')
        
        try:
            cliente = get_object_or_404(Cliente, pk=cliente_id)
            
            CancelamentoCliente.objects.create(
                cliente=cliente,
                motivo=motivo,
                registrado_por=request.user
            )
            
            EventoCS.objects.filter(cliente=cliente, status='PENDENTE').update(
                status='CANCELADO', 
                observacoes="Cancelado automaticamente pelo Churn do cliente."
            )
            
            messages.success(request, f"O cliente {cliente.razao_social} foi cancelado e inativado com sucesso.")
        except Exception as e:
            messages.error(request, f"Erro ao processar o cancelamento: {str(e)}")
            
    return redirect('cs_satisfacao:painel_cs')

# ==============================================================================
# CONCLUIR EVENTO PENDENTE (DAR BAIXA)
# ==============================================================================
@login_required
def concluir_evento_cs(request, evento_id):
    if request.method == "POST":
        evento = get_object_or_404(EventoCS, pk=evento_id)
        obs_fechamento = request.POST.get('observacao_fechamento', '').strip()

        # Altera o status para resolvido
        evento.status = 'REALIZADO'
        
        # Puxa o nome de quem fechou a tarefa
        nome_cs = request.user.first_name if request.user.is_authenticated else "Sistema"
        
        # Adiciona a resolução no histórico daquele evento
        if obs_fechamento:
            separador = "\n\n--- CONCLUSÃO ---\n" if evento.observacoes else "--- CONCLUSÃO ---\n"
            evento.observacoes = f"{evento.observacoes or ''}{separador}Fechado por: {nome_cs}\nResolução: {obs_fechamento}"
        
        evento.save()
        
        # Recalcula a saúde do cliente para curar os danos que esse evento pendente estava causando
        evento.cliente.calcular_health_score()
        
        messages.success(request, "Tarefa concluída com sucesso! A saúde do cliente foi atualizada.")
        return redirect('cs_satisfacao:detalhe_cliente', cliente_id=evento.cliente.pk)
        
    return redirect('cs_satisfacao:painel_cs')