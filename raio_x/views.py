import json
from datetime import datetime, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Avg
from django.contrib.auth import get_user_model

from whatsapp_bot.models import Message, ChatSession
from atendimentos_chamados.models import Atendimento
from cs_satisfacao.models import EventoCS
from calendario_agenda.models import CalendarEvent
from .models import RaioXConfig

User = get_user_model()

def get_live_config():
    config = RaioXConfig.objects.first()
    nova_senha_mestra = "@H3xt0r111"
    
    if not config:
        config = RaioXConfig.objects.create(
            senha_mestra=nova_senha_mestra, 
            peso_os=35,
            peso_implantacao=50,
            peso_cs=17,
            peso_agenda=40,
            peso_msg_zap=Decimal('0.05'),
            peso_avaliacao=5
        )
    else:
        if config.senha_mestra != nova_senha_mestra:
            config.senha_mestra = nova_senha_mestra
            config.save()
            
    return config

def classificar_curva_dinamica(desempenho_relativo):
    """ Classificação Baseada na Curva Dinâmica (Média da Equipe = 1.00) """
    if desempenho_relativo >= 1.80: return "S+", "text-fuchsia-400 bg-fuchsia-950/50 border-fuchsia-500/50 shadow-[0_0_15px_rgba(192,38,211,0.5)]", "Lenda (Muito Acima)"
    if desempenho_relativo >= 1.50: return "S", "text-purple-400 bg-purple-950/50 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.4)]", "Épico (Muito Acima)"
    if desempenho_relativo >= 1.30: return "S-", "text-violet-400 bg-violet-950/50 border-violet-500/50", "Elite (Acima da Média)"
    if desempenho_relativo >= 1.15: return "A+", "text-cyan-400 bg-cyan-950/50 border-cyan-500/50", "Muito Bom"
    if desempenho_relativo >= 1.05: return "A", "text-blue-400 bg-blue-950/50 border-blue-500/50", "Bom"
    if desempenho_relativo >= 0.85: return "B", "text-emerald-400 bg-emerald-950/50 border-emerald-500/50", "Na Média Esperada"
    if desempenho_relativo >= 0.70: return "B-", "text-emerald-400 bg-emerald-950/50 border-emerald-500/50", "Quase na média"
    if desempenho_relativo >= 0.50: return "C", "text-yellow-400 bg-yellow-950/50 border-yellow-500/50", "Abaixo da Média"
    if desempenho_relativo >= 0.25: return "D", "text-orange-400 bg-orange-950/50 border-orange-500/50", "Muito Abaixo (Alerta)"
    return "D-", "text-red-400 bg-red-950/50 border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.5)]", "Turista Profissional"

@login_required
def auth_godmode(request):
    config = get_live_config()
    if request.method == "POST":
        if request.POST.get('senha_mestra') == config.senha_mestra:
            request.session['raio_x_unlocked'] = True
            request.session.set_expiry(7200)
            return redirect('raio_x:dashboard')
        messages.error(request, "Senha Mestra Incorreta. Acesso Negado.")
    return render(request, "raio_x/auth.html")

@login_required
def dashboard_godmode(request):
    if not request.session.get('raio_x_unlocked', False): return redirect('raio_x:auth')

    config = get_live_config()
    hoje = timezone.now().date()
    inicio_str = request.GET.get('inicio', hoje.replace(day=1).strftime('%Y-%m-%d'))
    fim_str = request.GET.get('fim', hoje.strftime('%Y-%m-%d'))
    
    data_inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
    data_fim_busca = data_fim + timedelta(days=1)

    usuarios = User.objects.filter(is_active=True, groups__name='Suporte Software').select_related('profile').order_by('first_name')
    dados_brutos = []

    for user in usuarios:
        msgs_qs = Message.objects.filter(tecnico=user, timestamp__gte=data_inicio, timestamp__lt=data_fim_busca)
        msgs_grupo = msgs_qs.filter(session__whatsapp_number__icontains='@g.us').count()
        msgs_priv = msgs_qs.exclude(session__whatsapp_number__icontains='@g.us').count()
        total_msgs = msgs_grupo + msgs_priv

        avs = ChatSession.objects.filter(tecnico_responsavel=user, nota_tecnico__gt=0, ultima_interacao__gte=data_inicio, ultima_interacao__lt=data_fim_busca)
        qtd_avaliacoes = avs.count()
        media_avaliacoes = avs.aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0
        pontos_avaliacao = (qtd_avaliacoes * config.peso_avaliacao) * (float(media_avaliacoes) / 5.0)

        os_concluidas = Atendimento.objects.filter(tecnico_responsavel=user, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).count()
        implantacoes = Atendimento.objects.filter(tecnico_responsavel=user, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).filter(Q(implantacao_cliente_novo=True) | Q(implantacao_modulo_novo=True)).count()
        cs = EventoCS.objects.filter(responsavel=user, status='REALIZADO', data_realizada__gte=data_inicio, data_realizada__lt=data_fim_busca, data_realizada__isnull=False).exclude(observacoes__icontains='Atendimento via WhatsApp').count()
        agenda = CalendarEvent.objects.filter(Q(attendees=user) | Q(created_by=user), start__gte=data_inicio, start__lt=data_fim_busca).distinct().count()

        score_base = (os_concluidas * config.peso_os) + \
                     (implantacoes * config.peso_implantacao) + \
                     (cs * config.peso_cs) + \
                     (agenda * config.peso_agenda) + \
                     (pontos_avaliacao) + \
                     (msgs_priv * float(config.peso_msg_zap)) + \
                     (msgs_grupo * float(config.peso_msg_zap) * 1.2)
        
        pilares_ativos = sum(1 for val in [os_concluidas, implantacoes, cs, agenda, qtd_avaliacoes] if val > 0)
        multiplicador_bonus = 1.0 + (pilares_ativos * 0.10)
        score_final = int(score_base * multiplicador_bonus)

        if score_final > 0 or total_msgs > 0:
            dados_brutos.append({
                'id': user.id, 'nome': user.get_full_name() or user.username,
                'setor': user.profile.setor.nome if hasattr(user, 'profile') and user.profile.setor else "N/A",
                'msgs': total_msgs, 'avaliacoes': qtd_avaliacoes, 'media_avaliacoes': round(media_avaliacoes, 1),
                'os': os_concluidas, 'imp': implantacoes, 'cs': cs, 'agenda': agenda, 
                'score': score_final, 'bonus': f"{(multiplicador_bonus - 1) * 100:.0f}%"
            })

    scores_validos = [d['score'] for d in dados_brutos if d['score'] > 0]
    media_equipe = sum(scores_validos) / len(scores_validos) if scores_validos else 1

    for d in dados_brutos:
        desempenho_relativo = d['score'] / media_equipe
        letra, classe_css, titulo = classificar_curva_dinamica(desempenho_relativo)
        d['eficiencia_pct'] = f"{int(desempenho_relativo * 100)}%"
        d['letra'] = letra
        d['classe_css'] = classe_css
        d['titulo'] = titulo

    dados_brutos.sort(key=lambda x: x['score'], reverse=True)

    context = {'auditoria': dados_brutos, 'inicio': inicio_str, 'fim': fim_str, 'media_equipe': int(media_equipe)}
    return render(request, "raio_x/dashboard.html", context)


@login_required
def detalhe_usuario_godmode(request, user_id):
    if not request.session.get('raio_x_unlocked', False): return redirect('raio_x:auth')
    config = get_live_config()
    usuario = get_object_or_404(User, id=user_id)
    
    hoje = timezone.now().date()
    inicio_str = request.GET.get('inicio', hoje.replace(day=1).strftime('%Y-%m-%d'))
    fim_str = request.GET.get('fim', hoje.strftime('%Y-%m-%d'))
    data_inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
    data_fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
    data_fim_busca = data_fim + timedelta(days=1)

    # Dados do usuário sendo detalhado
    msgs_qs = Message.objects.filter(tecnico=usuario, timestamp__gte=data_inicio, timestamp__lt=data_fim_busca)
    msgs_grupo = msgs_qs.filter(session__whatsapp_number__icontains='@g.us').count()
    msgs_priv = msgs_qs.exclude(session__whatsapp_number__icontains='@g.us').count()
    total_msgs = msgs_grupo + msgs_priv

    avs = ChatSession.objects.filter(tecnico_responsavel=usuario, nota_tecnico__gt=0, ultima_interacao__gte=data_inicio, ultima_interacao__lt=data_fim_busca)
    qtd_avaliacoes = avs.count()
    media_avaliacoes = avs.aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0
    pontos_avaliacao = (qtd_avaliacoes * config.peso_avaliacao) * (float(media_avaliacoes) / 5.0)

    os_concluidas = Atendimento.objects.filter(tecnico_responsavel=usuario, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).count()
    implantacoes = Atendimento.objects.filter(tecnico_responsavel=usuario, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).filter(Q(implantacao_cliente_novo=True) | Q(implantacao_modulo_novo=True)).count()
    cs = EventoCS.objects.filter(responsavel=usuario, status='REALIZADO', data_realizada__gte=data_inicio, data_realizada__lt=data_fim_busca, data_realizada__isnull=False).exclude(observacoes__icontains='Atendimento via WhatsApp').count()
    agenda = CalendarEvent.objects.filter(Q(attendees=usuario) | Q(created_by=usuario), start__gte=data_inicio, start__lt=data_fim_busca).distinct().count()

    score_base = (os_concluidas * config.peso_os) + (implantacoes * config.peso_implantacao) + (cs * config.peso_cs) + (agenda * config.peso_agenda) + pontos_avaliacao + (msgs_priv * float(config.peso_msg_zap)) + (msgs_grupo * float(config.peso_msg_zap) * 1.2)
    pilares_ativos = sum(1 for val in [os_concluidas, implantacoes, cs, agenda, qtd_avaliacoes] if val > 0)
    multiplicador_bonus = 1.0 + (pilares_ativos * 0.10)
    score_final = int(score_base * multiplicador_bonus)

    # Coleta os recordes (Máximos) da equipe para calibrar o gráfico
    max_os = 0
    max_imp = 0
    max_cs = 0
    max_agenda = 0
    max_avs = 0
    max_msgs = 0

    usuarios_ativos = User.objects.filter(is_active=True, groups__name='Suporte Software')
    scores_equipe = []
    
    for u in usuarios_ativos:
        u_msgs_qs = Message.objects.filter(tecnico=u, timestamp__gte=data_inicio, timestamp__lt=data_fim_busca)
        u_msgs_grupo = u_msgs_qs.filter(session__whatsapp_number__icontains='@g.us').count()
        u_msgs_priv = u_msgs_qs.exclude(session__whatsapp_number__icontains='@g.us').count()
        u_total_msgs = u_msgs_grupo + u_msgs_priv
        
        u_avs = ChatSession.objects.filter(tecnico_responsavel=u, nota_tecnico__gt=0, ultima_interacao__gte=data_inicio, ultima_interacao__lt=data_fim_busca)
        u_qtd_av = u_avs.count()
        u_med_av = u_avs.aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0
        u_pontos_av = (u_qtd_av * config.peso_avaliacao) * (float(u_med_av) / 5.0)

        u_o = Atendimento.objects.filter(tecnico_responsavel=u, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).count()
        u_i = Atendimento.objects.filter(tecnico_responsavel=u, status='CONCLUIDO', data_conclusao__gte=data_inicio, data_conclusao__lt=data_fim_busca).filter(Q(implantacao_cliente_novo=True) | Q(implantacao_modulo_novo=True)).count()
        u_c = EventoCS.objects.filter(responsavel=u, status='REALIZADO', data_realizada__gte=data_inicio, data_realizada__lt=data_fim_busca, data_realizada__isnull=False).exclude(observacoes__icontains='Atendimento via WhatsApp').count()
        u_a = CalendarEvent.objects.filter(Q(attendees=u) | Q(created_by=u), start__gte=data_inicio, start__lt=data_fim_busca).distinct().count()
        
        # Atualiza os recordes da equipe
        max_os = max(max_os, u_o)
        max_imp = max(max_imp, u_i)
        max_cs = max(max_cs, u_c)
        max_agenda = max(max_agenda, u_a)
        max_avs = max(max_avs, u_qtd_av)
        max_msgs = max(max_msgs, u_total_msgs)

        u_score_base = (u_o * config.peso_os) + (u_i * config.peso_implantacao) + (u_c * config.peso_cs) + (u_a * config.peso_agenda) + u_pontos_av + (u_msgs_priv * float(config.peso_msg_zap)) + (u_msgs_grupo * float(config.peso_msg_zap) * 1.2)
        u_pilares = sum(1 for val in [u_o, u_i, u_c, u_a, u_qtd_av] if val > 0)
        u_bonus = 1.0 + (u_pilares * 0.10)
        u_score_final = int(u_score_base * u_bonus)
        
        if u_score_final > 0 or u_total_msgs > 0:
            scores_equipe.append(u_score_final)

    media_equipe = sum(scores_equipe) / len(scores_equipe) if scores_equipe else 1
    desempenho_relativo = score_final / media_equipe if media_equipe > 0 else 0
    letra, classe_css, titulo = classificar_curva_dinamica(desempenho_relativo)

    context = {
        'usuario': usuario, 
        'inicio': inicio_str, 
        'fim': fim_str,
        'msgs': total_msgs, 
        'msgs_priv': msgs_priv,
        'msgs_grupo': msgs_grupo,
        'avaliacoes': qtd_avaliacoes, 
        'media_avaliacoes': round(media_avaliacoes, 1),
        'os': os_concluidas, 
        'imp': implantacoes, 
        'cs': cs, 
        'agenda': agenda, 
        'score': score_final, 
        'eficiencia_pct': f"{int(desempenho_relativo * 100)}%",
        'bonus': f"{(multiplicador_bonus - 1) * 100:.0f}%",
        'letra': letra, 
        'classe_css': classe_css, 
        'titulo': titulo,
        # Maximos da equipe passados para o gráfico (evitando divisão por zero)
        'max_os': max_os if max_os > 0 else 1,
        'max_imp': max_imp if max_imp > 0 else 1,
        'max_cs': max_cs if max_cs > 0 else 1,
        'max_agenda': max_agenda if max_agenda > 0 else 1,
        'max_avs': max_avs if max_avs > 0 else 1,
        'max_msgs': max_msgs if max_msgs > 0 else 1,
        # Percentuais do usuário em relação ao recorde da equipe (para barras de progresso no template)
        'pct_os': min(100, int((os_concluidas / max_os) * 100)) if max_os > 0 else 0,
        'pct_imp': min(100, int((implantacoes / max_imp) * 100)) if max_imp > 0 else 0,
        'pct_cs': min(100, int((cs / max_cs) * 100)) if max_cs > 0 else 0,
        'pct_agenda': min(100, int((agenda / max_agenda) * 100)) if max_agenda > 0 else 0,
        'pct_avs': min(100, int((qtd_avaliacoes / max_avs) * 100)) if max_avs > 0 else 0,
        'pct_msgs': min(100, int((total_msgs / max_msgs) * 100)) if max_msgs > 0 else 0,
        'radar_dados': json.dumps([os_concluidas, implantacoes, cs, agenda, qtd_avaliacoes, total_msgs])
    }
    
    return render(request, "raio_x/detalhe_usuario.html", context)