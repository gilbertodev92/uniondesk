import json
import unicodedata
import requests
from collections import defaultdict
from datetime import date, datetime, timedelta
from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission, User
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from atendimentos_chamados.models import Atendimento
from clientes_sistemas.models import Cliente
from sistemas.models import Sistema
from whatsapp_bot.models import ChatSession, Message 
from cs_satisfacao.models import EventoCS, CancelamentoCliente
from .forms import ProfileForm, SistemaForm

# ==============================================================================
# GESTÃO DE USUÁRIOS E GRUPOS
# ==============================================================================
@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def painel_usuarios(request):
    usuarios = User.objects.all().order_by('username')
    grupos = Group.objects.all().order_by('name')
    sistemas = Sistema.objects.all()
    return render(request, 'users/painel_usuarios.html', {'usuarios': usuarios, 'grupos': grupos, 'sistemas': sistemas})

@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def painel_grupos(request):
    grupos = Group.objects.all().order_by('name')
    return render(request, 'users/painel_grupos.html', {'grupos': grupos})

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False, help_text="Deixe em branco para não alterar.")
    groups = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = User
        fields = ["username", "email", "is_active", "groups", "password"]
    def save(self, commit=True):
        user = super().save(commit=False)
        pwd = self.cleaned_data.get("password")
        if pwd: user.set_password(pwd)
        if commit:
            user.save()
            self.save_m2m()
        return user

@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def usuario_create(request):
    user_form = UserForm(request.POST or None)
    profile_form = ProfileForm(request.POST or None)
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user = user_form.save()
        profile = profile_form.save(commit=False)
        profile.user = user
        profile.save()
        messages.success(request, "Usuário criado com sucesso.")
        return redirect('painel_usuarios')
    return render(request, 'users/usuario_form.html', {'form': user_form, 'form_profile': profile_form, 'editando': False})

@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def usuario_edit(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    profile = getattr(usuario, 'profile', None)
    user_form = UserForm(request.POST or None, instance=usuario)
    profile_form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and user_form.is_valid() and profile_form.is_valid():
        user_form.save(); profile_form.save()
        messages.success(request, "Usuário atualizado com sucesso.")
        return redirect('painel_usuarios')
    return render(request, 'users/usuario_form.html', {'form': user_form, 'form_profile': profile_form, 'editando': True, 'obj': usuario})

class GroupForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(queryset=Permission.objects.all().order_by('content_type__app_label'), required=False, widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = Group
        fields = ["name", "permissions"]

@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def grupo_create(request):
    form = GroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grupo criado com sucesso.")
        return redirect('painel_grupos')
    return render(request, 'users/grupo_form.html', {'form': form})

@login_required
@permission_required('users.pode_ver_usuarios', raise_exception=True)
def grupo_edit(request, pk):
    grupo = get_object_or_404(Group, pk=pk) 
    form = GroupForm(request.POST or None, instance=grupo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grupo atualizado com sucesso.")
        return redirect('painel_grupos')
    return render(request, 'users/grupo_form.html', {'form': form, 'editando': True})


# ==============================================================================
# DASHBOARD DIGITAL (CENTRAL DE COMANDO)
# ==============================================================================
def calcular_meses_atras(data_base, qtd_meses):
    m = data_base.month - qtd_meses
    y = data_base.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)

@login_required
def home(request):
    hoje = timezone.now().date()
    
    periodo = request.GET.get('periodo', 'mes_exato')
    
    try:
        mes_selecionado = int(request.GET.get('mes', hoje.month))
        ano_selecionado = int(request.GET.get('ano', hoje.year))
    except ValueError:
        mes_selecionado = hoje.month
        ano_selecionado = hoje.year

    if periodo == 'ultimos_3':
        data_inicio = calcular_meses_atras(hoje, 2)
        data_fim = hoje + timedelta(days=1)
    elif periodo == 'ultimos_6':
        data_inicio = calcular_meses_atras(hoje, 5)
        data_fim = hoje + timedelta(days=1)
    elif periodo == 'este_ano':
        data_inicio = date(hoje.year, 1, 1)
        data_fim = hoje + timedelta(days=1)
    else:
        data_inicio = date(ano_selecionado, mes_selecionado, 1)
        if mes_selecionado == 12:
            data_fim = date(ano_selecionado + 1, 1, 1)
        else:
            data_fim = date(ano_selecionado, mes_selecionado + 1, 1)

    dia_str = request.GET.get('dia')
    if dia_str:
        try:
            dia_selecionado = datetime.strptime(dia_str, '%Y-%m-%d').date()
        except ValueError:
            dia_selecionado = hoje
    else:
        dia_selecionado = hoje
        
    usuarios = User.objects.all()
    status_resolvidos = ['FINALIZADO', 'AVALIACAO_TECNICO', 'AVALIACAO_NPS']

    # ==========================================================================
    # ABA 0: VISAO DIÁRIA (HOJE)
    # ==========================================================================
    ws_dia = ChatSession.objects.filter(ultima_interacao__date=dia_selecionado).exclude(status__icontains='DUPLICAD').exclude(whatsapp_number__icontains='@g.us')
    
    ws_dia_finalizados = ws_dia.filter(status__in=status_resolvidos).exclude(tecnico_responsavel__isnull=True).count()
    ws_dia_iniciados = ws_dia.exclude(status__in=status_resolvidos).exclude(tecnico_responsavel__isnull=True).count()
    
    ws_dia_tec_stats = []
    ws_dia_setores_dict = defaultdict(int)
    
    for u in usuarios:
        qtd_fechado_dia = ws_dia.filter(status__in=status_resolvidos, tecnico_responsavel=u).count()
        qtd_andamento_dia = ChatSession.objects.filter(status='EM_ATENDIMENTO', tecnico_responsavel=u).exclude(whatsapp_number__icontains='@g.us').count()
        
        if qtd_fechado_dia > 0 or qtd_andamento_dia > 0:
            ws_dia_tec_stats.append({
                'nome': (u.first_name if u.first_name else u.username).upper(),
                'concluidos': qtd_fechado_dia,
                'andamento': qtd_andamento_dia,
                'total': qtd_fechado_dia + qtd_andamento_dia
            })
        if qtd_fechado_dia > 0:
            setor_nome = "OUTROS"
            if hasattr(u, 'setor') and u.setor:
                setor_nome = getattr(u.setor, 'nome', str(u.setor))
            elif u.groups.exists():
                setor_nome = u.groups.first().name
            ws_dia_setores_dict[setor_nome.upper()] += qtd_fechado_dia
            
    ws_dia_tec_stats = sorted(ws_dia_tec_stats, key=lambda x: x['total'], reverse=True)[:7]

    os_dia_abertas = Atendimento.objects.filter(data_abertura__date=dia_selecionado).count()
    os_dia_resolvidas = Atendimento.objects.filter(data_conclusao__date=dia_selecionado, status='CONCLUIDO').count()
    
    os_dia_tec_stats = []
    for u in usuarios:
        qtd_fechado_dia_os = Atendimento.objects.filter(data_conclusao__date=dia_selecionado, status='CONCLUIDO', tecnico_responsavel=u).count()
        if qtd_fechado_dia_os > 0:
            os_dia_tec_stats.append({'nome': (u.first_name if u.first_name else u.username).upper(), 'resolvidas': qtd_fechado_dia_os})
            
    os_dia_tec_stats = sorted(os_dia_tec_stats, key=lambda x: x['resolvidas'], reverse=True)[:10]

    clientes_dia_interacoes = defaultdict(int)
    os_dia_qs = Atendimento.objects.filter(data_abertura__date=dia_selecionado)
    for os_obj in os_dia_qs.exclude(cliente__isnull=True).select_related('cliente'):
        clientes_dia_interacoes[os_obj.cliente.razao_social] += 1
    
    for chat_obj in ws_dia.exclude(status__in=status_resolvidos, tecnico_responsavel__isnull=True).exclude(cliente__isnull=True).select_related('cliente'):
        clientes_dia_interacoes[chat_obj.cliente.razao_social] += 1
    
    top_clientes_dia = sorted(clientes_dia_interacoes.items(), key=lambda x: x[1], reverse=True)[:10]

    msgs_grupos_dia = Message.objects.filter(
        timestamp__date=dia_selecionado,
        sender_type='TECNICO',
        session__whatsapp_number__icontains='@g.us'
    ).exclude(session__status__icontains='DUPLICAD').select_related('tecnico', 'session', 'session__cliente')
    
    atend_grp_dia_set = set() 
    tec_grp_dia = defaultdict(lambda: {'MANHA': 0, 'TARDE': 0, 'nome': ''})
    top_grp_dia_dict = defaultdict(int)
    
    for msg in msgs_grupos_dia:
        agora_local = timezone.localtime(msg.timestamp)
        is_tarde = agora_local.hour > 12 or (agora_local.hour == 12 and agora_local.minute > 30)
        turno = 'TARDE' if is_tarde else 'MANHA'
        
        tec_id = msg.tecnico.id if msg.tecnico else 0
        sess_id = msg.session.id
        
        chave_unica = (sess_id, tec_id, turno)
        if chave_unica not in atend_grp_dia_set:
            atend_grp_dia_set.add(chave_unica)
            if msg.tecnico:
                nome = msg.tecnico.first_name.upper() if msg.tecnico.first_name else msg.tecnico.username.upper()
                tec_grp_dia[tec_id]['nome'] = nome
                tec_grp_dia[tec_id][turno] += 1
            nome_grupo = msg.session.cliente.razao_social if msg.session.cliente else (msg.session.push_name or "Grupo Desconhecido")
            top_grp_dia_dict[nome_grupo] += 1
            
    grp_dia_labels_tec, grp_dia_dados_manha, grp_dia_dados_tarde = [], [], []
    for tec_id, data in sorted(tec_grp_dia.items(), key=lambda x: x[1]['MANHA'] + x[1]['TARDE'], reverse=True)[:7]:
        grp_dia_labels_tec.append(data['nome'])
        grp_dia_dados_manha.append(data['MANHA'])
        grp_dia_dados_tarde.append(data['TARDE'])
        
    top_grupos_dia_list = sorted(top_grp_dia_dict.items(), key=lambda x: x[1], reverse=True)[:10]


    # ==========================================================================
    # ABA 1: OPERAÇÃO WHATSAPP (MENSAL/PERÍODO)
    # ==========================================================================
    ws_mes = ChatSession.objects.filter(ultima_interacao__gte=data_inicio, ultima_interacao__lt=data_fim).exclude(status__icontains='DUPLICAD').exclude(whatsapp_number__icontains='@g.us')
    
    ws_concluidos = ws_mes.filter(status__in=status_resolvidos).exclude(tecnico_responsavel__isnull=True)
    ws_em_andamento = ws_mes.filter(status='EM_ATENDIMENTO').exclude(tecnico_responsavel__isnull=True)
    
    ws_fila_espera = ChatSession.objects.filter(status='PENDENTE').exclude(whatsapp_number__icontains='@g.us').count()
    ws_na_ia = ChatSession.objects.filter(status__in=['TRIAGEM', 'SUPORTE_IA']).exclude(whatsapp_number__icontains='@g.us').count()
    
    ws_total_mes = ws_concluidos.count() + ws_em_andamento.count()
    ws_media_geral = ws_concluidos.filter(nota_tecnico__gt=0).aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0

    ws_tecnicos_stats = []
    ws_setores_dict = defaultdict(int)

    for u in usuarios:
        t_concluidos = ws_concluidos.filter(tecnico_responsavel=u).count()
        t_andamento = ChatSession.objects.filter(status='EM_ATENDIMENTO', tecnico_responsavel=u).exclude(whatsapp_number__icontains='@g.us').count()
        t_nota = ws_concluidos.filter(tecnico_responsavel=u, nota_tecnico__gt=0).aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0
        
        if (t_concluidos + t_andamento) > 0 or t_nota > 0:
            ws_tecnicos_stats.append({'nome': (u.first_name if u.first_name else u.username).upper(),'concluidos': t_concluidos,'andamento': t_andamento,'total': t_concluidos + t_andamento,'nota': round(float(t_nota), 1)})
            
        if t_concluidos > 0:
            setor_nome = "OUTROS"
            if hasattr(u, 'setor') and u.setor:
                setor_nome = getattr(u.setor, 'nome', str(u.setor))
            elif u.groups.exists():
                setor_nome = u.groups.first().name
            ws_setores_dict[setor_nome.upper()] += t_concluidos

    ws_stats_ordenados = sorted(ws_tecnicos_stats, key=lambda x: x['total'], reverse=True)[:7]
    ws_stats_nota = sorted([t for t in ws_tecnicos_stats if t['nota'] > 0], key=lambda x: x['nota'], reverse=True)


    # ==========================================================================
    # ABA 2: RADAR OPS (O.S. MENSAL/PERÍODO)
    # ==========================================================================
    query_os_mes = Atendimento.objects.filter(data_abertura__gte=data_inicio, data_abertura__lt=data_fim)
    os_concluidos = Atendimento.objects.filter(status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim)
    os_abertos = Atendimento.objects.filter(data_abertura__gte=data_inicio, data_abertura__lt=data_fim).exclude(status='CONCLUIDO')
    
    os_total_abertos = os_abertos.count()
    os_total_concluidos = os_concluidos.count()
    implantacoes_ativas = os_abertos.filter(Q(implantacao_cliente_novo=True) | Q(implantacao_modulo_novo=True)).count()

    labels_vol_os, dados_vol_os, dados_vol_fechados_os = [], [], []
    
    abertas_qs = Atendimento.objects.filter(data_abertura__gte=data_inicio, data_abertura__lt=data_fim)\
        .annotate(dia=TruncDate('data_abertura')).values('dia').annotate(qtd=Count('numero')).order_by('dia')
    dict_abertas = {item['dia']: item['qtd'] for item in abertas_qs if item['dia']}
    
    fechadas_qs = Atendimento.objects.filter(data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim, status='CONCLUIDO')\
        .annotate(dia=TruncDate('data_conclusao')).values('dia').annotate(qtd=Count('numero')).order_by('dia')
    dict_fechadas = {item['dia']: item['qtd'] for item in fechadas_qs if item['dia']}
    
    data_ref = hoje if (mes_selecionado == hoje.month and ano_selecionado == hoje.year) else (data_fim - timedelta(days=1))
    delta_dias = (data_ref - data_inicio).days

    for i in range(delta_dias + 1):
        dia_atual = data_inicio + timedelta(days=i)
        labels_vol_os.append(dia_atual.strftime('%d/%m'))
        dados_vol_os.append(dict_abertas.get(dia_atual, 0))
        dados_vol_fechados_os.append(dict_fechadas.get(dia_atual, 0))

    prio_critica = os_abertos.filter(prioridade='CRITICA').count()
    prio_alta = os_abertos.filter(prioridade='ALTA').count()
    prio_media = os_abertos.filter(prioridade='MEDIA').count()
    prio_baixa = os_abertos.filter(prioridade='BAIXA').count()
    
    os_tecnicos_pendentes = []
    for u in usuarios:
        qtd_pendente = os_abertos.filter(tecnico_responsavel=u).count()
        qtd_concluida = os_concluidos.filter(tecnico_responsavel=u).count()
        if qtd_pendente > 0 or qtd_concluida > 0:
            os_tecnicos_pendentes.append({'nome': (u.first_name if u.first_name else u.username).upper(),'qtd': qtd_pendente,'qtd_concluida': qtd_concluida})
            
    os_tecnicos_pendentes = sorted(os_tecnicos_pendentes, key=lambda x: x['qtd'] + x.get('qtd_concluida', 0), reverse=True)[:10]
    setores_stats = query_os_mes.exclude(setor_atual__isnull=True).values('setor_atual__nome').annotate(total=Count('numero')).order_by('-total')


    # ==========================================================================
    # ABA 3: GRUPOS VIP (MENSAL/PERÍODO)
    # ==========================================================================
    msgs_grupos_mes = Message.objects.filter(
        timestamp__gte=data_inicio,
        timestamp__lt=data_fim,
        sender_type='TECNICO',
        session__whatsapp_number__icontains='@g.us'
    ).exclude(session__status__icontains='DUPLICAD').select_related('tecnico', 'session', 'session__cliente')
    
    atend_grp_mes_set = set() 
    tec_grp_mes = defaultdict(lambda: {'MANHA': 0, 'TARDE': 0, 'nome': ''})
    top_grp_mes_dict = defaultdict(int)
    
    for msg in msgs_grupos_mes:
        agora_local = timezone.localtime(msg.timestamp)
        is_tarde = agora_local.hour > 12 or (agora_local.hour == 12 and agora_local.minute > 30)
        turno = 'TARDE' if is_tarde else 'MANHA'
        dia_msg = agora_local.date()
        
        tec_id = msg.tecnico.id if msg.tecnico else 0
        sess_id = msg.session.id
        
        chave_unica_mes = (sess_id, tec_id, turno, dia_msg)
        if chave_unica_mes not in atend_grp_mes_set:
            atend_grp_mes_set.add(chave_unica_mes)
            if msg.tecnico:
                nome = msg.tecnico.first_name.upper() if msg.tecnico.first_name else msg.tecnico.username.upper()
                tec_grp_mes[tec_id]['nome'] = nome
                tec_grp_mes[tec_id][turno] += 1
            nome_grupo = msg.session.cliente.razao_social if msg.session.cliente else (msg.session.push_name or "Grupo Desconhecido")
            top_grp_mes_dict[nome_grupo] += 1
            
    total_interacoes_vip_mes = len(atend_grp_mes_set)
    grp_mes_labels_tec, grp_mes_dados_manha, grp_mes_dados_tarde = [], [], []
    
    for tec_id, data in sorted(tec_grp_mes.items(), key=lambda x: x[1]['MANHA'] + x[1]['TARDE'], reverse=True)[:7]:
        grp_mes_labels_tec.append(data['nome'])
        grp_mes_dados_manha.append(data['MANHA'])
        grp_mes_dados_tarde.append(data['TARDE'])
        
    top_grupos_mes_list = sorted(top_grp_mes_dict.items(), key=lambda x: x[1], reverse=True)[:10]


    # ==========================================================================
    # ABA 4: CUSTOMER SUCCESS E CHURN (LÓGICA DO AVIÃO)
    # ==========================================================================
    base_clientes_ativos = Cliente.objects.filter(ativo=True)
    clientes_ativos = base_clientes_ativos.count()
    clientes_inativos = Cliente.objects.filter(ativo=False).count()
    
    try:
        novos_clientes_qs = Cliente.objects.filter(data_criacao__gte=data_inicio, data_criacao__lt=data_fim)
        qtd_novos = novos_clientes_qs.count()
        novos_por_sistema = novos_clientes_qs.values('sistemas__nome').annotate(total=Count('pk'))
    except Exception as e:
        print(f"Erro ao buscar novos clientes: {e}")
        qtd_novos = 0
        novos_clientes_qs = Cliente.objects.none()
        novos_por_sistema = []
        
    try:
        cancelamentos_qs = CancelamentoCliente.objects.filter(data_cancelamento__gte=data_inicio, data_cancelamento__lt=data_fim)
        qtd_churn = cancelamentos_qs.count()
        cancelados_por_sistema = cancelamentos_qs.values('cliente__sistemas__nome').annotate(total=Count('pk'))
    except Exception as e:
        print(f"Erro ao buscar cancelamentos: {e}")
        qtd_churn = 0
        cancelados_por_sistema = []

    saldo_crescimento = qtd_novos - qtd_churn
    
    if saldo_crescimento > 0:
        cor_aviao = "#22c55e"
        status_aviao = "GANHANDO ALTURA"
        rotacao_aviao = "-45deg"
    elif saldo_crescimento < 0:
        cor_aviao = "#ef4444"
        status_aviao = "PERDENDO ALTURA"
        rotacao_aviao = "45deg"
    else:
        cor_aviao = "#9ca3af"
        status_aviao = "EM VOO DE CRUZEIRO"
        rotacao_aviao = "0deg"

    sistemas_nomes = set()
    dict_novos = defaultdict(int)
    dict_cancelados = defaultdict(int)

    for item in novos_por_sistema:
        nome = item.get('sistemas__nome') or 'Outros'
        sistemas_nomes.add(nome)
        dict_novos[nome] += item['total']
    for item in cancelados_por_sistema:
        nome = item.get('cliente__sistemas__nome') or 'Outros'
        sistemas_nomes.add(nome)
        dict_cancelados[nome] += item['total']

    lista_sistemas_churn = sorted(list(sistemas_nomes))
    dados_novos_sis = [dict_novos[sys] for sys in lista_sistemas_churn]
    dados_cancelados_sis = [dict_cancelados[sys] for sys in lista_sistemas_churn]

    nps_geral = base_clientes_ativos.aggregate(Avg('health_score'))['health_score__avg'] or 0
    hs_critico = base_clientes_ativos.filter(health_score__lt=50).count()
    hs_atencao = base_clientes_ativos.filter(health_score__gte=50, health_score__lt=75).count()
    hs_saudavel = base_clientes_ativos.filter(health_score__gte=75).count()
    
    clientes_interacoes = defaultdict(int)
    for os_obj in query_os_mes.exclude(cliente__isnull=True).select_related('cliente'):
        clientes_interacoes[os_obj.cliente.razao_social] += 1
        
    for chat_obj in ChatSession.objects.filter(ultima_interacao__gte=data_inicio, ultima_interacao__lt=data_fim).exclude(status__icontains='DUPLICAD').exclude(status__in=status_resolvidos, tecnico_responsavel__isnull=True).exclude(cliente__isnull=True).select_related('cliente'):
        clientes_interacoes[chat_obj.cliente.razao_social] += 1
        
    top_clientes = sorted(clientes_interacoes.items(), key=lambda x: x[1], reverse=True)[:7]

    ws_avaliados = ws_concluidos.filter(nota_tecnico__gt=0)
    nps_promotores = ws_avaliados.filter(nota_nps__gte=9).count()
    nps_neutros = ws_avaliados.filter(nota_nps__gte=7, nota_nps__lte=8).count()
    nps_detratores = ws_avaliados.filter(nota_nps__lte=6).count()
    total_avaliacoes = nps_promotores + nps_neutros + nps_detratores
    score_nps = round(((nps_promotores - nps_detratores) / total_avaliacoes) * 100) if total_avaliacoes > 0 else 0

    detratores_qs = ws_avaliados.filter(nota_nps__lte=6).select_related('cliente', 'tecnico_responsavel').order_by('-ultima_interacao')[:20]
    lista_detratores = []
    for chat in detratores_qs:
        nome_cliente = chat.cliente.razao_social if chat.cliente else chat.whatsapp_number
        nome_tec = chat.tecnico_responsavel.first_name if chat.tecnico_responsavel and chat.tecnico_responsavel.first_name else (chat.tecnico_responsavel.username if chat.tecnico_responsavel else "Desconhecido")
        lista_detratores.append({
            'cliente': nome_cliente,
            'tecnico': nome_tec,
            'nota_nps': chat.nota_nps,
            'nota_tec': chat.nota_tecnico,
            'data': chat.ultima_interacao.strftime('%d/%m %H:%M')
        })

    classificacao_abc = base_clientes_ativos.values('faturamento_cliente').annotate(total=Count('codigo')).order_by('faturamento_cliente')
    labels_abc, dados_abc = [], []
    mapa_abc = {'A': 'A - Alta', 'B': 'B - Média', 'C': 'C - Baixa', 'D': 'D - Muito Baixa'}
    for item in classificacao_abc:
        labels_abc.append(mapa_abc.get(item['faturamento_cliente'], 'Não Classificado'))
        dados_abc.append(item['total'])

    qtd_backup = base_clientes_ativos.filter(backup_contratado=True).count()
    qtd_hospedagem = base_clientes_ativos.filter(hospedagem_datacenter=True).count()
    qtd_hardware = base_clientes_ativos.filter(contrato_hardware=True).count()
    fin_em_dia = base_clientes_ativos.filter(status_financeiro='EM_DIA').count()
    fin_pendente = base_clientes_ativos.filter(status_financeiro='PENDENTE').count()

    meses_lista = [(1, 'Jan'), (2, 'Fev'), (3, 'Mar'), (4, 'Abr'), (5, 'Mai'), (6, 'Jun'), (7, 'Jul'), (8, 'Ago'), (9, 'Set'), (10, 'Out'), (11, 'Nov'), (12, 'Dez')]

    # ==========================================================================
    # INTELIGÊNCIA GEOGRÁFICA - MAPA E TABELA POR SISTEMAS
    # ==========================================================================
    def remover_acentos(texto):
        if not texto: return ""
        texto_limpo = ''.join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')
        return texto_limpo.strip().upper()

    base_ativos = Cliente.objects.filter(ativo=True, cidade__isnull=False).exclude(cidade='')
    
    mapa_dados = {'TOTAL': defaultdict(int)}
    tabela_cidades = defaultdict(list)
    sistemas_encontrados = set()

    for cliente in base_ativos.prefetch_related('sistemas'):
        cidade_nome = remover_acentos(cliente.cidade)
        sistemas_cliente = [s.nome.upper() for s in cliente.sistemas.all()]
        
        mapa_dados['TOTAL'][cidade_nome] += 1
        
        for sis in sistemas_cliente:
            if sis not in mapa_dados:
                mapa_dados[sis] = defaultdict(int)
            mapa_dados[sis][cidade_nome] += 1
            sistemas_encontrados.add(sis)
        
        cidade_exibicao = cliente.cidade.strip().upper() 
        tabela_cidades[cidade_exibicao].append({
            'nome': cliente.razao_social,
            'sistemas': ", ".join(sistemas_cliente),
            'telefone': cliente.telefone
        })

    tabela_ordenada = dict(sorted(tabela_cidades.items()))
    lista_sistemas_mapa = sorted(list(sistemas_encontrados))
    # ==========================================================================
    # DETALHAMENTO DE CLIENTES POR SISTEMA
    # ==========================================================================
    tabela_sistemas = defaultdict(list)
    for cliente in base_ativos.prefetch_related('sistemas'):
        sistemas_cliente = [s.nome.upper() for s in cliente.sistemas.all()]
        if not sistemas_cliente: continue
        
        cidade_exibicao = cliente.cidade.strip().upper() if cliente.cidade else 'NÃO INFORMADA'
        
        for sis in sistemas_cliente:
            tabela_sistemas[sis].append({
                'nome': cliente.razao_social,
                'cidade': cidade_exibicao,
                'telefone': cliente.telefone
            })
            
    tabela_sistemas_ordenada = dict(sorted(tabela_sistemas.items()))

    # ==========================================================================
    # NOVOS GRÁFICOS CS: PRODUTIVIDADE, ATRASOS E CLIENTES ATENDIDOS
    # ==========================================================================
    cs_realizados_mes = EventoCS.objects.filter(status='REALIZADO', data_realizada__gte=data_inicio, data_realizada__lt=data_fim)
    
    cs_tec_stats = cs_realizados_mes.exclude(responsavel__isnull=True).values('responsavel__first_name', 'responsavel__username').annotate(total=Count('id')).order_by('-total')[:7]
    cs_labels_tec = [(t['responsavel__first_name'] or t['responsavel__username']).upper() for t in cs_tec_stats]
    cs_dados_tec = [t['total'] for t in cs_tec_stats]

    cs_pend_tec_stats = EventoCS.objects.filter(status='PENDENTE', data_prevista__lt=hoje).exclude(responsavel__isnull=True).values('responsavel__first_name', 'responsavel__username').annotate(total=Count('id')).order_by('-total')[:7]
    cs_labels_pend_tec = [(t['responsavel__first_name'] or t['responsavel__username']).upper() for t in cs_pend_tec_stats]
    cs_dados_pend_tec = [t['total'] for t in cs_pend_tec_stats]

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

    context = {
        'periodo': periodo,
        'mes_atual': mes_selecionado, 'ano_atual': ano_selecionado, 'meses_lista': meses_lista,
        'cs_labels_tec': json.dumps(cs_labels_tec),
        'cs_dados_tec': json.dumps(cs_dados_tec),
        'cs_labels_pend_tec': json.dumps(cs_labels_pend_tec),
        'cs_dados_pend_tec': json.dumps(cs_dados_pend_tec),
        'clientes_cs_mes': clientes_cs_mes,
        'dia_selecionado': dia_selecionado.strftime('%Y-%m-%d'),
        'dia_selecionado_formatado': dia_selecionado.strftime('%d/%m/%Y'),
        'ws_diario_iniciados': ws_dia_iniciados, 'ws_diario_finalizados': ws_dia_finalizados,
        'os_diario_abertas': os_dia_abertas, 'os_diario_resolvidas': os_dia_resolvidas,
        'ws_dia_labels_tec': json.dumps([t['nome'] for t in ws_dia_tec_stats]),
        'ws_dia_dados_concluidos': json.dumps([t['concluidos'] for t in ws_dia_tec_stats]),
        'ws_dia_dados_andamento': json.dumps([t['andamento'] for t in ws_dia_tec_stats]),
        'os_dia_labels_tec': json.dumps([t['nome'] for t in os_dia_tec_stats]),
        'os_dia_dados_resolvidas': json.dumps([t['resolvidas'] for t in os_dia_tec_stats]),
        'dia_labels_top': json.dumps([c[0] for c in top_clientes_dia]),
        'dia_dados_top': json.dumps([c[1] for c in top_clientes_dia]),
        'ws_dia_labels_setor': json.dumps(list(ws_dia_setores_dict.keys())),
        'ws_dia_dados_setor': json.dumps(list(ws_dia_setores_dict.values())),
        
        'grp_dia_labels_tec': json.dumps(grp_dia_labels_tec),
        'grp_dia_dados_manha': json.dumps(grp_dia_dados_manha),
        'grp_dia_dados_tarde': json.dumps(grp_dia_dados_tarde),
        'grp_dia_labels_top': json.dumps([c[0] for c in top_grupos_dia_list]),
        'grp_dia_dados_top': json.dumps([c[1] for c in top_grupos_dia_list]),
        
        'ws_total_mes': ws_total_mes, 'ws_concluidos_count': ws_concluidos.count(),
        'ws_andamento_count': ws_em_andamento.count(), 'ws_fila_espera': ws_fila_espera,
        'ws_na_ia': ws_na_ia, 'ws_media_geral': round(float(ws_media_geral), 1),
        'ws_labels_tech': json.dumps([t['nome'] for t in ws_stats_ordenados]),
        'ws_dados_concluidos': json.dumps([t['concluidos'] for t in ws_stats_ordenados]),
        'ws_dados_andamento': json.dumps([t['andamento'] for t in ws_stats_ordenados]),
        'ws_labels_nota': json.dumps([t['nome'] for t in ws_stats_nota]),
        'ws_dados_nota': json.dumps([t['nota'] for t in ws_stats_nota]),
        'ws_labels_setor': json.dumps(list(ws_setores_dict.keys())),
        'ws_dados_setor': json.dumps(list(ws_setores_dict.values())),
        
        'os_concluidos_count': os_total_concluidos, 'os_abertos_count': os_total_abertos,
        'os_prio_critica': prio_critica, 'os_implantacoes': implantacoes_ativas,
        'os_labels_vol': json.dumps(labels_vol_os), 'os_dados_vol': json.dumps(dados_vol_os),
        'os_dados_vol_fechados': json.dumps(dados_vol_fechados_os), 
        'os_dados_prio': json.dumps([prio_critica, prio_alta, prio_media, prio_baixa]),
        'os_labels_tec_pendentes': json.dumps([t['nome'] for t in os_tecnicos_pendentes]),
        'os_dados_tec_pendentes': json.dumps([t['qtd'] for t in os_tecnicos_pendentes]),
        'os_dados_tec_fechados': json.dumps([t.get('qtd_concluida', 0) for t in os_tecnicos_pendentes]), 
        'os_labels_setor': json.dumps([s['setor_atual__nome'] for s in setores_stats]),
        'os_dados_setor': json.dumps([s['total'] for s in setores_stats]),
        
        'total_interacoes_vip_mes': total_interacoes_vip_mes,
        'grp_mes_labels_tec': json.dumps(grp_mes_labels_tec),
        'grp_mes_dados_manha': json.dumps(grp_mes_dados_manha),
        'grp_mes_dados_tarde': json.dumps(grp_mes_dados_tarde),
        'grp_mes_labels_top': json.dumps([c[0] for c in top_grupos_mes_list]),
        'grp_mes_dados_top': json.dumps([c[1] for c in top_grupos_mes_list]),

        'qtd_detratores': nps_detratores,
        'lista_detratores': lista_detratores,
        'nps_geral': round(float(nps_geral), 1), 'clientes_ativos': clientes_ativos,
        'cs_dados_risco': json.dumps([hs_critico, hs_atencao, hs_saudavel]),
        'cs_labels_top': json.dumps([c[0] for c in top_clientes]),
        'cs_dados_top': json.dumps([c[1] for c in top_clientes]),
        'cs_dados_nps': json.dumps([nps_promotores, nps_neutros, nps_detratores]),
        'score_nps': score_nps, 'cs_labels_abc': json.dumps(labels_abc),
        'cs_dados_abc': json.dumps(dados_abc),
        'cs_dados_servicos': json.dumps([qtd_backup, qtd_hospedagem, qtd_hardware]),
        'cs_dados_financeiro': json.dumps([fin_em_dia, fin_pendente]),
        
        'mapa_dados_json': json.dumps(mapa_dados),
        'tabela_cidades': tabela_ordenada,
        'tabela_sistemas': tabela_sistemas_ordenada,
        'lista_sistemas_mapa': lista_sistemas_mapa,
        
        'cs_dados_ativos_inativos': json.dumps([clientes_ativos, clientes_inativos]),
        'qtd_novos': qtd_novos,
        'qtd_churn': qtd_churn,
        'saldo_crescimento': saldo_crescimento,
        'cor_aviao': cor_aviao,
        'status_aviao': status_aviao,
        'rotacao_aviao': rotacao_aviao,
        'churn_labels_sis': json.dumps(lista_sistemas_churn),
        'churn_dados_novos_sis': json.dumps(dados_novos_sis),
        'churn_dados_cancelados_sis': json.dumps(dados_cancelados_sis),
    }
    return render(request, "dashboard.html", context)

# ==============================================================================
# LOGIN / LOGOUT / RELATORIOS
# ==============================================================================
def user_login(request):
    if request.user.is_authenticated:
        return redirect('/setup/')

    if request.method == "POST":
        # --- INÍCIO DA VALIDAÇÃO DO CAPTCHA ---
        turnstile_response = request.POST.get('cf-turnstile-response')
        turnstile_secret = '0x4AAAAAAD1Dd-MhgeQ76ZAmbyhk03Bk1Vw' 
        
        if not turnstile_response:
            messages.error(request, "Falha de segurança. A validação do Captcha é obrigatória.")
            return render(request, "users/login.html")

        try:
            cf_req = requests.post(
                'https://challenges.cloudflare.com/turnstile/v0/siteverify',
                data={
                    'secret': turnstile_secret,
                    'response': turnstile_response,
                    'remoteip': request.META.get('REMOTE_ADDR')
                },
                timeout=5
            )
            cf_result = cf_req.json()

            if not cf_result.get('success'):
                messages.error(request, "Verificação de segurança falhou. Tente novamente.")
                return render(request, "users/login.html")
                
        except requests.RequestException:
            messages.error(request, "Erro ao conectar com o serviço de segurança. Tente novamente.")
            return render(request, "users/login.html")
        # --- FIM DA VALIDAÇÃO DO CAPTCHA ---

        u, p = request.POST.get("username"), request.POST.get("password")
        user = authenticate(request, username=u, password=p)
        
        if user: 
            login(request, user)
            next_url = request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('/setup/')
            
        messages.error(request, "Usuário ou senha inválidos.")
        
    return render(request, "users/login.html")

@login_required
def user_logout(request): 
    logout(request)
    return redirect('/')

@login_required
def relatorio_cidade(request):
    cidade_nome = request.GET.get('cidade', '')
    if not cidade_nome:
        return redirect('home')

    clientes = Cliente.objects.filter(ativo=True, cidade__iexact=cidade_nome).prefetch_related('sistemas').order_by('razao_social')
    
    context = {
        'cidade': cidade_nome.upper(),
        'clientes': clientes,
        'data_geracao': timezone.now()
    }
    return render(request, "relatorio_cidade.html", context)

import csv
from django.http import HttpResponse

@login_required
def relatorio_cidade_excel(request):
    cidade_nome = request.GET.get('cidade', '')
    if not cidade_nome:
        return redirect('home')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="clientes_{cidade_nome}.csv"'
    
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response, delimiter=';')
    
    writer.writerow(['Razão Social', 'Telefone', 'CNPJ', 'Sistemas'])

    clientes = Cliente.objects.filter(ativo=True, cidade__iexact=cidade_nome).prefetch_related('sistemas').order_by('razao_social')
    
    for c in clientes:
        sistemas_str = ", ".join([s.nome for s in c.sistemas.all()])
        telefone = getattr(c, 'telefone', '') or ''
        cnpj = getattr(c, 'cnpj', '') or ''
        writer.writerow([c.razao_social, telefone, cnpj, sistemas_str])

    return response


@login_required
def relatorio_sistema(request):
    sistema_nome = request.GET.get('sistema', '')
    if not sistema_nome:
        return redirect('home')

    clientes = Cliente.objects.filter(ativo=True, sistemas__nome__iexact=sistema_nome).prefetch_related('sistemas').order_by('razao_social')
    
    context = {
        'sistema': sistema_nome.upper(),
        'clientes': clientes,
        'data_geracao': timezone.now()
    }
    
    return render(request, "relatorio_sistema.html", context)


@login_required
def relatorio_sistema_excel(request):
    sistema_nome = request.GET.get('sistema', '')
    if not sistema_nome:
        return redirect('home')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="clientes_{sistema_nome}.csv"'
    
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response, delimiter=';')
    
    writer.writerow(['Razão Social', 'Cidade', 'Telefone', 'CNPJ', 'Sistemas'])

    clientes = Cliente.objects.filter(ativo=True, sistemas__nome__iexact=sistema_nome).prefetch_related('sistemas').order_by('razao_social')
    
    for c in clientes:
        sistemas_str = ", ".join([s.nome for s in c.sistemas.all()])
        cidade = getattr(c, 'cidade', '') or ''
        telefone = getattr(c, 'telefone', '') or ''
        cnpj = getattr(c, 'cnpj', '') or ''
        writer.writerow([c.razao_social, cidade, telefone, cnpj, sistemas_str])

    return response