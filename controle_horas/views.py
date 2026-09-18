from datetime import date, time, timedelta
from decimal import Decimal
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import AgendaEvento
from django.contrib.auth import get_user_model
import csv
from whatsapp_bot.views import enviar_msg_whatsapp
from whatsapp_bot.models import ChatSession
from atendimentos_chamados.models import Atendimento  # Ajuste para o nome real do seu model de chamados
from cs_satisfacao.models import EventoCS
from clientes_sistemas.models import Cliente
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth.models import User
from .forms import ApontamentoForm
from .models import Apontamento

User = get_user_model()

# -------------------------
# Constantes do WhatsApp (usadas nas notificações de ponto)
# -------------------------
ID_GRUPO_SUPORTE = "120363191864718007@g.us"
NUMERO_GERENTE = "5547992573078@s.whatsapp.net"  # Número formatado para a API

# -------------------------
# Helpers & Segurança
# -------------------------

# 🔥 NOSSA FECHADURA ELETRÔNICA (Agora blindada para o RH)
def is_rh_ou_gestor(user):
    """Retorna True se for Chefão ou se estiver nos grupos autorizados (RH/Gestor)"""
    return user.is_superuser or user.groups.filter(name__in=["Administrador", "Gestor", "RH"]).exists()

def is_admin_master(user):
    """
    🔒 Fechadura da Escala (Agenda / 'Escala Rápida').
    Só o Administrador (superusuário) pode agendar/remover Home Office,
    Plantão, Férias e Folga Compensada de qualquer colaborador.
    Gestor/RH continuam com as demais permissões (aprovações, fechamento),
    mas não editam mais a Escala.
    """
    return user.is_superuser

def tem_home_office_hoje(user, dia):
    """True se o colaborador tiver Home Office agendado na Escala para 'dia'."""
    return AgendaEvento.objects.filter(
        funcionario=user, data=dia, tipo='home_office'
    ).exists()

# ═══════════════════════════════════════════════════════════════════════
# PLANTÃO
# Igual ao home office, o plantão precisa estar AGENDADO na escala (tipo
# 'plantao'). Mas o botão só libera DENTRO da janela de plantão:
#   • Segunda a sexta: 18:00 às 23:00
#   • Sábado:          07:00 às 23:00
#   • Domingo:         não há plantão
# (O home office continua valendo no expediente normal, 07:00 às 18:00.)
# ═══════════════════════════════════════════════════════════════════════
PLANTAO_SEMANA_INICIO = time(18, 0)   # seg-sex começa às 18:00
PLANTAO_SABADO_INICIO = time(7, 0)    # sábado começa às 07:00
PLANTAO_FIM           = time(23, 0)   # todos terminam às 23:00

def tem_plantao_hoje(user, dia):
    """True se o colaborador tiver Plantão agendado na Escala para 'dia'."""
    return AgendaEvento.objects.filter(
        funcionario=user, data=dia, tipo='plantao'
    ).exists()

def dentro_janela_plantao(dia, hora_atual):
    """
    True se 'hora_atual' cai na janela de plantão daquele dia da semana.
    Domingo (weekday 6) nunca tem plantão.
    """
    wd = dia.weekday()  # 0=seg ... 5=sáb, 6=dom
    if wd == 6:
        return False
    inicio = PLANTAO_SABADO_INICIO if wd == 5 else PLANTAO_SEMANA_INICIO
    return inicio <= hora_atual <= PLANTAO_FIM

def pode_bater_plantao_agora(user, dia, hora_atual):
    """Plantão liberado = está agendado E está dentro da janela do dia."""
    return tem_plantao_hoje(user, dia) and dentro_janela_plantao(dia, hora_atual)

def is_rh_setor(user):
    """
    🔒 Lançamento e edição manual de ponto (o modal "Lançamento manual" e o
    lápis de editar rascunho/reprovado): só quem está no Setor "RH"
    (Profile.setor, cadastrado em Usuários) tem permissão — permite ajustar
    manualmente qualquer horário, então não pode ficar liberado pra todo mundo.
    Superusuário sempre passa, pra nunca ficar destrancado de si mesmo.
    """
    if user.is_superuser:
        return True
    perfil = getattr(user, 'profile', None)
    setor = getattr(perfil, 'setor', None)
    nome_setor = (getattr(setor, 'nome', '') or '').strip().upper()
    return nome_setor == 'RH'

# 🌙 Janela de Atualização: fora do horário comercial, 18:30 até 07:30 do dia seguinte.
JANELA_ATUALIZACAO_INICIO = time(18, 30)
JANELA_ATUALIZACAO_FIM = time(7, 30)

def dentro_janela_atualizacao(hora_atual):
    """
    True se 'hora_atual' estiver dentro da janela noturna de Atualização
    (18:30 às 07:30). Como a janela cruza a meia-noite, é OR e não AND.
    """
    return hora_atual >= JANELA_ATUALIZACAO_INICIO or hora_atual < JANELA_ATUALIZACAO_FIM

def _hhmm(dec):
    if dec is None: return "00:00"
    dec = Decimal(dec)
    total_min = int(round(dec * 60))
    hh = total_min // 60
    mm = total_min % 60
    return f"{hh:02d}:{mm:02d}"


# =====================================================================
# COCKPIT ÚNICO (SPA) - NÍVEL NASA
# =====================================================================
@login_required
def cockpit_horas(request):
    hoje = timezone.localdate()
    
    # 1. Filtros Globais de Competência
    competencia = request.GET.get("competencia", hoje.strftime("%Y-%m"))
    try:
        ano, mes = map(int, competencia.split("-"))
    except:
        ano, mes = hoje.year, hoje.month

    # Gera lista dos últimos 6 meses para o filtro
    opcoes_meses = []
    _y, _m = hoje.year, hoje.month
    for _ in range(6):
        opcoes_meses.append({
            "valor": f"{_y:04d}-{_m:02d}",
            "label": f"{_m:02d}/{_y}",
        })
        _m -= 1
        if _m == 0:
            _m = 12
            _y -= 1

    # 2. Dados da Aba: MEU PONTO
    meus_aponts = Apontamento.objects.filter(usuario=request.user, data__year=ano, data__month=mes).annotate(
        inicio=Coalesce("manha_inicio", "tarde_inicio", "especial_inicio")
    ).order_by("-data", "-inicio")
    
    total_h_meu = sum((a.horas_total or Decimal("0.00") for a in meus_aponts), start=Decimal("0.00"))
    extra_h_meu = sum((a.horas_extra or Decimal("0.00") for a in meus_aponts), start=Decimal("0.00"))

    status_atual = "Fora do expediente"
    status_cor = "neutral"          # neutral | active | pause | done
    proximo_label = "Marcar Entrada"
    proximo_sub = "Início da jornada"
    pode_bater_ponto = (ano == hoje.year and mes == hoje.month)

    # 🔒 Só libera o botão de Home Office se houver vínculo na Escala hoje
    tem_escala_home_office_hoje = tem_home_office_hoje(request.user, hoje)

    # 🌙 Plantão: agendado hoje E dentro da janela (seg-sex 18h-23h, sáb 7h-23h).
    # Usa a hora REAL de agora, não a competência selecionada no topo.
    _agora_plantao = timezone.localtime(timezone.now())
    tem_plantao_agendado_hoje = tem_plantao_hoje(request.user, hoje)
    pode_bater_plantao_hoje = pode_bater_plantao_agora(request.user, hoje, _agora_plantao.time())

    # 🌙 Janela de Atualização (18:30–07:30): sempre calculada pela hora REAL de agora,
    # independente do filtro de competência selecionado no topo da página.
    agora_local_real = timezone.localtime(timezone.now())
    pode_registrar_atualizacao = dentro_janela_atualizacao(agora_local_real.time())
    clientes_ativos = Cliente.objects.filter(ativo=True).order_by("razao_social").only(
        "codigo", "razao_social", "nome_fantasia"
    )

    # 🔄 Ciclo de Atualização em aberto hoje (início batido, fim ainda não)?
    # Se sim, o botão vira "Finalizar Atualização" e não precisa mais
    # escolher cliente — é só fechar o ciclo que já está andando.
    atualizacao_aberta = Apontamento.objects.filter(
        usuario=request.user, data=hoje, tipo=Apontamento.TIPO_ATUALIZACAO,
        especial_inicio__isnull=False, especial_fim__isnull=True,
    ).select_related('cliente_atualizacao').order_by('id').last()
    atualizacao_em_aberto = atualizacao_aberta is not None
    atualizacao_cliente_atual = (
        atualizacao_aberta.cliente_atualizacao.razao_social
        if atualizacao_aberta and atualizacao_aberta.cliente_atualizacao else None
    )

    if pode_bater_ponto:
        ponto_normal_hoje = Apontamento.objects.filter(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_NORMAL
        ).order_by('id').last()
        ponto_especial_hoje = Apontamento.objects.filter(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_EMERGENCIA
        ).order_by('id').last()
 
        if not ponto_normal_hoje:
            proximo_label, proximo_sub = "Marcar Entrada", "Início da manhã"
        elif not ponto_normal_hoje.manha_inicio:
            proximo_label, proximo_sub = "Marcar Entrada", "Início da manhã"
        elif not ponto_normal_hoje.manha_fim:
            status_atual, status_cor = "Trabalhando agora", "active"
            proximo_label, proximo_sub = "Marcar Saída", "Início do almoço"
        elif not ponto_normal_hoje.tarde_inicio:
            status_atual, status_cor = "Em pausa (almoço)", "pause"
            proximo_label, proximo_sub = "Marcar Volta", "Retorno do almoço"
        elif not ponto_normal_hoje.tarde_fim:
            status_atual, status_cor = "Trabalhando agora", "active"
            proximo_label, proximo_sub = "Marcar Saída", "Fim do expediente"
        else:
            status_atual, status_cor = "Expediente encerrado", "done"
            if ponto_especial_hoje and ponto_especial_hoje.especial_inicio and not ponto_especial_hoje.especial_fim:
                status_atual, status_cor = "Atendimento especial em andamento", "active"
                proximo_label, proximo_sub = "Marcar Fim", "Fim do atendimento especial"
            else:
                proximo_label, proximo_sub = "Registrar Atendimento", "Atendimento especial / plantão"

    # 3. Permissões e Dados do Gestor/RH
    is_gestor = is_rh_ou_gestor(request.user)
    aprovacoes_pendentes = []
    resumo_fechamento = []

    if is_gestor:
        # Aba: APROVAÇÕES
        aprovacoes_pendentes = Apontamento.objects.filter(
            status="pendente", data__year=ano, data__month=mes
        ).select_related("usuario").order_by("usuario__username", "-data")

        # Aba: FECHAMENTOS & RELATÓRIOS
        resumo_fechamento = Apontamento.objects.filter(status="aprovado", data__year=ano, data__month=mes)\
            .values("usuario__id", "usuario__username", "usuario__first_name", "usuario__last_name")\
            .annotate(total_h=Coalesce(Sum("horas_total"), Value(Decimal("0.00"))),
                      extra_h=Coalesce(Sum("horas_extra"), Value(Decimal("0.00"))))\
            .order_by("usuario__username")

    context = {
        "ano": ano, "mes": mes, "competencia": competencia, "opcoes_meses": opcoes_meses,
        "meus_aponts": meus_aponts, "total_h_meu": total_h_meu, "extra_h_meu": extra_h_meu,
        "is_gestor": is_gestor, "aprovacoes_pendentes": aprovacoes_pendentes, "resumo_fechamento": resumo_fechamento,
        "form_manual": ApontamentoForm(),
        # NOVO:
        "hoje": hoje,
        "status_atual": status_atual,
        "status_cor": status_cor,
        "proximo_label": proximo_label,
        "proximo_sub": proximo_sub,
        "pode_bater_ponto": pode_bater_ponto,
        "tem_escala_home_office_hoje": tem_escala_home_office_hoje,
        "tem_plantao_agendado_hoje": tem_plantao_agendado_hoje,
        "pode_bater_plantao_hoje": pode_bater_plantao_hoje,
        "is_admin_master": is_admin_master(request.user),
        "is_rh_setor": is_rh_setor(request.user),
        "pode_registrar_atualizacao": pode_registrar_atualizacao,
        "clientes_ativos": clientes_ativos,
        "atualizacao_em_aberto": atualizacao_em_aberto,
        "atualizacao_cliente_atual": atualizacao_cliente_atual,
    }
    return render(request, "controle_horas/cockpit.html", context)

# =====================================================================
# AÇÕES DE BATER PONTO E CRUD (Redirecionam de volta pro Cockpit)
# =====================================================================
from django.utils.http import url_has_allowed_host_and_scheme

def _redirect_seguro(request, fallback='controle_horas:painel'):
    """
    Redireciona para request.GET['next'] se for uma URL segura (mesmo host),
    senão cai no fallback. Usado pra voltar o usuário pra onde ele estava
    (ex.: chat_mobile do whatsapp_bot) depois de bater o ponto, sem precisar
    mexer na view de origem.
    """
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect(fallback)

def _bater_ponto_plantao(request, hoje, hora_atual):
    """
    Registra o ponto de PLANTÃO como tipo plantão (2 marcações: início e fim).
    Chamado pelo bater_ponto_rapido quando o usuário tem plantão agendado e
    está dentro da janela de horário do dia.
    """
    ponto = Apontamento.objects.filter(
        usuario=request.user, data=hoje, tipo=Apontamento.TIPO_PLANTAO
    ).order_by('id').last()

    if not ponto:
        ponto = Apontamento.objects.create(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_PLANTAO, status='pendente'
        )

    if not ponto.especial_inicio:
        ponto.especial_inicio = hora_atual
        label = "Início do Plantão"
        iniciou = True
    elif not ponto.especial_fim:
        ponto.especial_fim = hora_atual
        label = "Fim do Plantão"
        iniciou = False
    else:
        messages.error(request, "O plantão de hoje já foi iniciado e encerrado.")
        return _redirect_seguro(request)

    ponto.status = 'pendente'
    ponto.save()

    hora_str = hora_atual.strftime('%H:%M')
    messages.success(request, f"Plantão: {label} às {hora_str}")

    # notifica o grupo, no mesmo espírito do ponto normal
    nome_tecnico = request.user.first_name or request.user.username
    if iniciou:
        msg = f"🚀 *{nome_tecnico}* iniciou o plantão às {hora_str}."
    else:
        msg = f"🌙 *{nome_tecnico}* encerrou o plantão às {hora_str}."
    try:
        enviar_msg_whatsapp(ID_GRUPO_SUPORTE, msg)
    except Exception as e:
        print(f"Erro ao enviar notificação de plantão: {e}")

    return _redirect_seguro(request)


@login_required
def bater_ponto_rapido(request):
    agora_local = timezone.localtime(timezone.now())
    hoje = agora_local.date()
    hora_atual = agora_local.time()

    # 🔒 TRAVA DE ESCALA — dois caminhos para liberar o botão:
    #   1) HOME OFFICE agendado hoje → expediente normal (4 marcações).
    #   2) PLANTÃO agendado hoje E dentro da janela de plantão → registra
    #      como plantão (2 marcações). Seg-sex 18h-23h, sáb 7h-23h, dom nunca.
    liberado_home_office = tem_home_office_hoje(request.user, hoje)
    liberado_plantao = pode_bater_plantao_agora(request.user, hoje, hora_atual)

    if not liberado_home_office and not liberado_plantao:
        # mensagem específica: se tem plantão agendado mas está fora da hora,
        # avisa o horário certo em vez de mandar procurar o RH.
        if tem_plantao_hoje(request.user, hoje):
            wd = hoje.weekday()
            if wd == 6:
                msg = "Não há plantão aos domingos."
            else:
                ini = PLANTAO_SABADO_INICIO if wd == 5 else PLANTAO_SEMANA_INICIO
                msg = (f"Seu plantão de hoje pode ser registrado das "
                       f"{ini.strftime('%H:%M')} às {PLANTAO_FIM.strftime('%H:%M')}.")
            messages.warning(request, msg)
        else:
            messages.warning(
                request,
                "Hoje você não possui expediente de Home Office nem Plantão agendado. "
                "O expediente deveria ser presencial. Em caso de dúvidas, "
                "entre em contato com o setor de Recursos Humanos."
            )
        return _redirect_seguro(request)

    # ── PLANTÃO: registra como tipo plantão (2 marcações: início e fim) ──
    # Só entra aqui se NÃO houver home office no dia (home office tem
    # prioridade e usa o fluxo normal de 4 marcações abaixo).
    if liberado_plantao and not liberado_home_office:
        return _bater_ponto_plantao(request, hoje, hora_atual)

    ponto = Apontamento.objects.filter(
        usuario=request.user, data=hoje, tipo=Apontamento.TIPO_NORMAL
    ).order_by('id').last()

    if not ponto:
        ponto = Apontamento.objects.create(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_NORMAL, status='pendente'
        )

    label = ""
    is_fim_expediente = False

    if not ponto.manha_inicio:
        ponto.manha_inicio = hora_atual
        label = "Entrada Manhã"
    elif not ponto.manha_fim:
        ponto.manha_fim = hora_atual
        label = "Saída Manhã (Almoço)"
    elif not ponto.tarde_inicio:
        ponto.tarde_inicio = hora_atual
        label = "Entrada Tarde"
    elif not ponto.tarde_fim:
        ponto.tarde_fim = hora_atual
        label = "Saída Tarde (Fim)"
        is_fim_expediente = True
    else:
        ponto_esp = Apontamento.objects.filter(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_EMERGENCIA
        ).order_by('id').last()
        
        if not ponto_esp:
            ponto_esp = Apontamento.objects.create(
                usuario=request.user, data=hoje, tipo=Apontamento.TIPO_EMERGENCIA, status='pendente'
            )

        if not ponto_esp.especial_inicio:
            ponto_esp.especial_inicio = hora_atual
            label = "Início Especial"
        elif not ponto_esp.especial_fim:
            ponto_esp.especial_fim = hora_atual
            label = "Fim Especial"
            is_fim_expediente = True
        else:
            messages.error(request, "Limite de batidas diárias atingido.")
            return _redirect_seguro(request)
        
        ponto_esp.status = 'pendente' 
        ponto_esp.save() 
        messages.success(request, f"Ponto ESPECIAL: {label} às {hora_atual.strftime('%H:%M')}")

    if not label.endswith("Especial"):
        ponto.status = 'pendente'
        ponto.save()
        messages.success(request, f"Ponto registrado: {label} às {hora_atual.strftime('%H:%M')}")

    # =========================================================
    # MÁGICA DO WHATSAPP: NOTIFICAÇÃO E RELATÓRIO DO DIA
    # =========================================================
    nome_tecnico = request.user.first_name or request.user.username
    hora_str = hora_atual.strftime('%H:%M')

    # 1. Notificação Inteligente e Conversacional
    is_fim_de_semana = hoje.weekday() >= 5 # 5=Sábado, 6=Domingo
    is_pos_horario = hora_atual.hour > 18 or (hora_atual.hour == 18 and hora_atual.minute >= 30)
    is_plantao = is_fim_de_semana or is_pos_horario

    if is_plantao:
        if "Entrada" in label or "Início" in label:
            msg_notificacao = f"🚀 *{nome_tecnico}* iniciou o plantão às {hora_str}."
        else:
            msg_notificacao = f"🌙 *{nome_tecnico}* encerrou o plantão às {hora_str}."
    else:
        if label == "Entrada Manhã":
            msg_notificacao = f"☀️ *{nome_tecnico}* iniciou o expediente às {hora_str}."
        elif label == "Saída Manhã (Almoço)":
            msg_notificacao = f"🍽️ *{nome_tecnico}* saiu para o almoço às {hora_str}."
        elif label == "Entrada Tarde":
            msg_notificacao = f"💻 *{nome_tecnico}* retornou do almoço às {hora_str}."
        elif label == "Saída Tarde (Fim)":
            msg_notificacao = f"🏠 *{nome_tecnico}* encerrou o expediente às {hora_str}."
        elif label == "Início Especial":
            msg_notificacao = f"🚨 *{nome_tecnico}* iniciou um atendimento especial às {hora_str}."
        elif label == "Fim Especial":
            msg_notificacao = f"✅ *{nome_tecnico}* finalizou o atendimento especial às {hora_str}."
        else:
            msg_notificacao = f"⏱️ *{nome_tecnico}* registrou o ponto às {hora_str}."
    
    try:
        enviar_msg_whatsapp(ID_GRUPO_SUPORTE, msg_notificacao)
    except Exception as e:
        print(f"Erro ao enviar notificação de ponto: {e}")

    # 2. Relatório de Fim de Expediente (Vai para o GERENTE no privado)
    if is_fim_expediente:
        try:
            # Sessoes de Bot: Exclui IDs que terminam em @g.us (que são de grupos)
            sessoes_bot = ChatSession.objects.filter(
                tecnico_responsavel=request.user, 
                ultima_interacao__date=hoje
            ).exclude(whatsapp_number__endswith='@g.us').count()
            
            # Atendimentos de Grupos: Filtra apenas IDs que terminam em @g.us
            atendimentos_grupos = ChatSession.objects.filter(
                tecnico_responsavel=request.user, 
                ultima_interacao__date=hoje,
                whatsapp_number__endswith='@g.us'
            ).count()
            
            # Eventos CS: Usa responsavel e REALIZADO
            eventos_cs = EventoCS.objects.filter(
                responsavel=request.user, 
                status='REALIZADO', 
                data_realizada=hoje
            ).count()
            
            # OS / Chamados: Usa tecnico_responsavel e CONCLUIDO
            os_fechadas = Atendimento.objects.filter(
                tecnico_responsavel=request.user, 
                status='CONCLUIDO', 
                data_conclusao__date=hoje
            ).count()
            
            relatorio = (
                f"*Relatório do dia*\n"
                f"Tecnico: {nome_tecnico}\n"
                f"Atendimentos no Bot (sessoes): {sessoes_bot} quantidade\n"
                f"Atendimentos de grupos: {atendimentos_grupos} atendimentos\n"
                f"Eventos CS realizados: {eventos_cs} eventos\n"
                f"Atendimento OS fechadas hoje: {os_fechadas} atendimentos"
            )
            
            enviar_msg_whatsapp(NUMERO_GERENTE, relatorio)
        except Exception as e:
            print(f"Erro ao gerar/enviar relatório do dia: {e}")

    return _redirect_seguro(request)


# =====================================================================
# BATER PONTO DE ATUALIZAÇÃO (vincula um Cliente, fora do horário comercial)
# =====================================================================
@login_required
def bater_ponto_atualizacao(request):
    """
    Botão dedicado para Atualização de cliente feita fora do horário
    comercial (18:30–07:30). Diferente do plantão genérico, aqui o
    colaborador escolhe QUAL cliente está sendo atualizado, e essa
    informação vai junto na notificação do grupo do WhatsApp.

    Suporta múltiplas atualizações na mesma madrugada: cada vez que um
    ciclo (início + fim) é fechado, a próxima batida abre um registro novo
    para o próximo cliente.
    """
    agora_local = timezone.localtime(timezone.now())
    hoje = agora_local.date()
    hora_atual = agora_local.time()

    # 🔒 TRAVA DE HORÁRIO: só funciona fora do expediente comercial.
    if not dentro_janela_atualizacao(hora_atual):
        messages.warning(
            request,
            "Registro de Atualização disponível apenas fora do horário comercial "
            "(das 18:30 às 07:30). Durante o expediente (07:30–18:30) o atendimento "
            "ao cliente é feito normalmente, sem precisar bater esse ponto especial."
        )
        return redirect('controle_horas:painel')

    if request.method != 'POST':
        return redirect('controle_horas:painel')

    cliente_id = request.POST.get('cliente_id')
    cliente = Cliente.objects.filter(pk=cliente_id).first() if cliente_id else None

    # Pega o último registro de Atualização de hoje (se existir e ainda estiver
    # "em aberto", ou seja, com início mas sem fim, continuamos nele).
    ponto_esp = Apontamento.objects.filter(
        usuario=request.user, data=hoje, tipo=Apontamento.TIPO_ATUALIZACAO
    ).order_by('id').last()

    ciclo_fechado = (not ponto_esp) or (ponto_esp.especial_inicio and ponto_esp.especial_fim)

    if ciclo_fechado:
        # Começando uma atualização nova (a primeira do dia, ou mais uma depois
        # de uma já finalizada) -> obrigatório informar o cliente.
        if not cliente:
            messages.error(request, "Selecione o cliente que será atualizado para registrar o ponto.")
            return redirect('controle_horas:painel')

        ponto_esp = Apontamento.objects.create(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_ATUALIZACAO,
            status='pendente', cliente_atualizacao=cliente,
            especial_inicio=hora_atual,
        )
        label = "Início Atualização"
    elif not ponto_esp.especial_inicio:
        if not cliente:
            messages.error(request, "Selecione o cliente que será atualizado para registrar o ponto.")
            return redirect('controle_horas:painel')
        ponto_esp.especial_inicio = hora_atual
        ponto_esp.cliente_atualizacao = cliente
        ponto_esp.status = 'pendente'
        ponto_esp.save()
        label = "Início Atualização"
    else:
        # Fechando o ciclo em aberto -> não precisa reenviar o cliente.
        ponto_esp.especial_fim = hora_atual
        ponto_esp.status = 'pendente'
        ponto_esp.save()
        label = "Fim Atualização"

    cliente_nome = ponto_esp.cliente_atualizacao.razao_social if ponto_esp.cliente_atualizacao else "Cliente não informado"
    nome_tecnico = request.user.first_name or request.user.username
    hora_str = hora_atual.strftime('%H:%M')

    if label == "Início Atualização":
        msg_notificacao = f"🔧 *{nome_tecnico}* iniciou uma ATUALIZAÇÃO no cliente *{cliente_nome}* às {hora_str}."
    else:
        msg_notificacao = f"✅ *{nome_tecnico}* finalizou a ATUALIZAÇÃO no cliente *{cliente_nome}* às {hora_str}."

    messages.success(request, msg_notificacao.replace('*', ''))

    try:
        enviar_msg_whatsapp(ID_GRUPO_SUPORTE, msg_notificacao)
    except Exception as e:
        print(f"Erro ao enviar notificação de atualização: {e}")

    return redirect('controle_horas:painel')


@login_required
def apontamento_create(request):
    # 🔒 Lançamento manual: só o Setor RH tem permissão.
    if not is_rh_setor(request.user):
        messages.warning(
            request,
            "Apenas o setor de Recursos Humanos tem permissão para lançamento manual de horas. "
            "Em caso de necessidade, entre em contato com o RH."
        )
        return redirect("controle_horas:painel")

    if request.method == "POST":
        form = ApontamentoForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.usuario = request.user
            obj.status = "pendente"
            obj.save()
            messages.success(request, "Lançamento manual enviado para aprovação.")
    return redirect("controle_horas:painel")

@login_required
def apontamento_edit(request, pk):
    # 🔒 Edição manual de um lançamento já existente: mesma regra do
    # "Lançamento manual" — só RH. Sem essa trava aqui, dava pra contornar
    # o bloqueio de cima batendo o ponto normal e depois editando os horários.
    if not is_rh_setor(request.user):
        messages.warning(
            request,
            "Apenas o setor de Recursos Humanos tem permissão para editar manualmente um lançamento. "
            "Em caso de necessidade, entre em contato com o RH."
        )
        return redirect("controle_horas:painel")

    obj = get_object_or_404(Apontamento, pk=pk, usuario=request.user, status__in=["pendente", "reprovado"])
    if request.method == "POST":
        form = ApontamentoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.status = "pendente"
            obj.save()
            messages.success(request, "Ponto corrigido e enviado para aprovação.")
    return redirect("controle_horas:painel")

@login_required
def apontamento_delete(request, pk):
    obj = get_object_or_404(Apontamento, pk=pk, usuario=request.user, status__in=["pendente", "reprovado"])
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Lançamento excluído com sucesso.")
    return redirect("controle_horas:painel")

# =====================================================================
# AÇÕES DO RH/GESTOR (Aprovar / Reprovar)
# =====================================================================
@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def apontamento_aprovar(request, pk):
    obj = get_object_or_404(Apontamento, pk=pk, status="pendente")
    obj.status = "aprovado"; obj.aprovado_por = request.user; obj.aprovado_em = timezone.now(); obj.save()
    return redirect(request.META.get("HTTP_REFERER", "controle_horas:painel"))

@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def apontamento_reprovar(request, pk):
    obj = get_object_or_404(Apontamento, pk=pk, status="pendente")
    obj.status = "reprovado"; obj.aprovado_por = request.user; obj.aprovado_em = timezone.now(); obj.save()
    messages.warning(request, f"Ponto de {obj.usuario.username} reprovado para correção.")
    return redirect(request.META.get("HTTP_REFERER", "controle_horas:painel"))


# =====================================================================
# PDF E EXPORTAÇÕES (HTML NASA STYLE - BLINDADOS)
# =====================================================================
@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def export_csv_mes(request, ano, mes):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="apontamentos_{int(ano):04d}-{int(mes):02d}.csv"'
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Usuario", "Data", "Tipo", "Horas", "Horas Extra", "Status", "Descricao"])
    qs = Apontamento.objects.filter(data__year=ano, data__month=mes, status="aprovado").select_related("usuario").order_by("usuario__username", "data")
    for a in qs:
        writer.writerow([a.usuario.get_full_name() or a.usuario.username, a.data.strftime("%Y-%m-%d"), a.get_tipo_display(), _hhmm(a.horas_total), _hhmm(a.horas_extra), a.get_status_display(), (a.descricao or "").replace("\n", " ").strip()])
    return response

@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def relatorio_espelho_individual_pdf(request, user_id):
    """Gera o HTML do Ponto de um ÚNICO funcionário"""
    competencia = request.GET.get("competencia")
    hoje = timezone.localdate()
    if not competencia:
        competencia = hoje.strftime("%Y-%m")
    
    try:
        ano, mes = map(int, competencia.split("-"))
    except:
        ano, mes = hoje.year, hoje.month

    usuario = get_object_or_404(User, id=user_id)
    
    aponts = Apontamento.objects.filter(
        usuario=usuario, data__year=ano, data__month=mes, status="aprovado"
    ).order_by('data')

    rows = []
    for a in aponts:
        rows.append({
            'data': a.data,
            'e1': a.manha_inicio,
            's1': a.manha_fim,
            'e2': a.tarde_inicio if a.tipo == 'normal' else a.especial_inicio,
            's2': a.tarde_fim if a.tipo == 'normal' else a.especial_fim,
            'total': a.horas_total,
            'extra': a.horas_extra,
            'descricao': a.descricao,
            'tipo': a.get_tipo_display()
        })

    context = {
        'usuario': usuario,
        'competencia': competencia,
        'rows': rows
    }
    return render(request, "controle_horas/relatorios/espelho_pdf.html", context)

@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def relatorio_espelho_mes_pdf(request):
    """Gera o HTML CONSOLIDADO de TODOS os funcionários do mês"""
    competencia = request.GET.get("competencia")
    hoje = timezone.localdate()
    if not competencia:
        competencia = hoje.strftime("%Y-%m")
    
    try:
        ano, mes = map(int, competencia.split("-"))
    except:
        ano, mes = hoje.year, hoje.month

    usuarios_ids = Apontamento.objects.filter(
        status="aprovado", data__year=ano, data__month=mes
    ).values_list('usuario', flat=True).distinct()

    relatorios = []
    for user_id in usuarios_ids:
        usuario = User.objects.get(id=user_id)
        aponts = Apontamento.objects.filter(
            usuario=usuario, data__year=ano, data__month=mes, status="aprovado"
        ).order_by('data')

        rows = []
        for a in aponts:
            rows.append({
                'data': a.data,
                'e1': a.manha_inicio if a.tipo == 'normal' else a.especial_inicio,
                's1': a.manha_fim if a.tipo == 'normal' else a.especial_fim,
                'e2': a.tarde_inicio if a.tipo == 'normal' else None,
                's2': a.tarde_fim if a.tipo == 'normal' else None,
                'total': a.horas_total,
                'extra': a.horas_extra,
                'descricao': a.descricao,
                'tipo': a.get_tipo_display()
            })
        
        relatorios.append({
            'usuario': usuario,
            'rows': rows
        })

    context = {
        'competencia': competencia,
        'relatorios': relatorios
    }
    return render(request, "controle_horas/relatorios/espelho_consolidado_pdf.html", context)

@login_required
@user_passes_test(is_rh_ou_gestor, login_url='/controle-horas/painel/')
def export_relatorio_mes_pdf(request, ano, mes):
    return HttpResponse("Função de PDF Consolidado em implementação. Use o Espelho de Ponto (A4).")

@login_required
def api_meu_status_ponto(request):
    """
    Endpoint leve pra qualquer tela (ex.: chat_mobile, que é de outro app)
    consultar via JS se o usuário logado pode bater ponto de Home Office
    hoje e se está dentro da janela de Atualização — sem precisar duplicar
    essa lógica em outro app nem tocar na view de lá.
    """
    agora_local = timezone.localtime(timezone.now())
    hoje = agora_local.date()
    hora_atual = agora_local.time()
    return JsonResponse({
        "tem_home_office_hoje": tem_home_office_hoje(request.user, hoje),
        "pode_registrar_atualizacao": dentro_janela_atualizacao(hora_atual),
        "tem_plantao_agendado_hoje": tem_plantao_hoje(request.user, hoje),
        "pode_bater_plantao_hoje": pode_bater_plantao_agora(request.user, hoje, hora_atual),
        "hora_atual": hora_atual.strftime("%H:%M"),
    })


@login_required
def api_eventos_agenda(request):
    """Retorna os eventos no formato que o FullCalendar exige"""
    eventos = AgendaEvento.objects.all().select_related('funcionario')
    dados = []
    
    for ev in eventos:
        # Define as cores baseadas no tipo de evento
        if ev.tipo == 'plantao':
            cor_bg = '#d97706'  # Laranja
        elif ev.tipo == 'home_office':
            cor_bg = '#4f46e5'  # Roxo/Índigo
        elif ev.tipo == 'ferias':
            cor_bg = "#e623bb"  # Verde Esmeralda
        elif ev.tipo == 'folga_compensada':
            cor_bg = "#0e7500"  # Azul Claro
        else:
            cor_bg = '#64748b'  # Cinza padrão de segurança
        
        dados.append({
            'id': ev.id,
            'title': f"{ev.funcionario.first_name or ev.funcionario.username}",
            'start': ev.data.strftime('%Y-%m-%d'),
            'color': cor_bg,
            'textColor': '#ffffff',
            'allDay': True
        })
        
    return JsonResponse(dados, safe=False)

@login_required
@csrf_exempt
def salvar_evento_agenda(request):
    """Salva de forma rápida o plantonista clicando no dia"""
    if not is_admin_master(request.user):
        return JsonResponse({'status': 'erro', 'message': 'Sem permissão. Apenas o Administrador pode editar a Escala.'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            usuario_id = data.get('usuario_id')
            data_evento = data.get('data')
            tipo = data.get('tipo', 'plantao')
            
            if not usuario_id or not data_evento:
                return JsonResponse({'status': 'erro', 'message': 'Dados incompletos'}, status=400)
                
            funcionario = User.objects.get(id=usuario_id)
            
            AgendaEvento.objects.update_or_create(
                funcionario=funcionario,
                data=data_evento,
                defaults={'tipo': tipo}
            )
            return JsonResponse({'status': 'sucesso'})
        except Exception as e:
            return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalido'}, status=405)

@login_required
@csrf_exempt
def remover_evento_agenda(request):
    """Remove o evento ao clicar nele"""
    if not is_admin_master(request.user):
        return JsonResponse({'status': 'erro', 'message': 'Sem permissão. Apenas o Administrador pode editar a Escala.'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            evento_id = data.get('evento_id')
            AgendaEvento.objects.filter(id=evento_id).delete()
            return JsonResponse({'status': 'sucesso'})
        except Exception as e:
            return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'invalido'}, status=405)