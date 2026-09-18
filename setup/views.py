from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import ComunicadoInterno
from whatsapp_bot.models import ChatSession
from atendimentos_chamados.models import Atendimento

@login_required
def home(request):
    # Pega todos os nomes dos grupos que o usuário logado faz parte
    nomes_grupos = list(request.user.groups.values_list('name', flat=True))
    
    # Se o cara for chefe, ele vê a fila de TUDO
    is_admin = request.user.is_superuser or 'Admins' in nomes_grupos or 'Irrestrito' in nomes_grupos

    # ==========================================
    # 1. WHATSAPP (CHATS)
    # ==========================================
    meus_chats = ChatSession.objects.filter(
        tecnico_responsavel=request.user,
        status='EM_ATENDIMENTO'
    ).count()

    if is_admin:
        fila_setor = ChatSession.objects.filter(status='PENDENTE').count()
    else:
        setor_zap_filtro = Q()
        if hasattr(request.user, 'setor') and request.user.setor:
            setor_zap_filtro |= Q(setor_atual=str(request.user.setor).upper())
        
        # Mapeia os grupos do Django para os setores do Zap
        for grupo in nomes_grupos:
            g_lower = grupo.lower()
            if 'suporte' in g_lower: setor_zap_filtro |= Q(setor_atual='SUPORTE')
            if 'comercial' in g_lower: setor_zap_filtro |= Q(setor_atual='COMERCIAL')
            if 'financeiro' in g_lower: setor_zap_filtro |= Q(setor_atual='FINANCEIRO')
            if 'assist' in g_lower: setor_zap_filtro |= Q(setor_atual='ASSISTENCIA')

        if setor_zap_filtro:
            fila_setor = ChatSession.objects.filter(Q(status='PENDENTE') & setor_zap_filtro).count()
        else:
            fila_setor = 0

    # ==========================================
    # 2. O.S. / CHAMADOS
    # ==========================================
    minhas_os = Atendimento.objects.filter(
        tecnico_responsavel=request.user
    ).exclude(status='CONCLUIDO').count()

    if is_admin:
        os_fila_setor = Atendimento.objects.filter(
            tecnico_responsavel__isnull=True
        ).exclude(status='CONCLUIDO').count()
    else:
        setor_os_filtro = Q()
        if hasattr(request.user, 'setor') and request.user.setor:
            setor_os_filtro |= Q(setor_atual=request.user.setor)
        
        if nomes_grupos:
            # A MÁGICA AQUI: Puxa O.S. onde o nome do setor_atual bate com algum grupo do cara
            setor_os_filtro |= Q(setor_atual__nome__in=nomes_grupos)
            
        if setor_os_filtro:
            os_fila_setor = Atendimento.objects.filter(
                setor_os_filtro, 
                tecnico_responsavel__isnull=True
            ).exclude(status='CONCLUIDO').count()
        else:
            os_fila_setor = 0

    # ==========================================
    # 3. NÍVEL E XP (Puxando da sua CARTEIRA)
    # ==========================================
    try:
        from recompensas.models import Carteira
        carteira = Carteira.objects.filter(usuario=request.user).first()
        if carteira:
            nivel_atual = carteira.nivel_atual
            xp_atual = carteira.xp_total
            xp_proximo = carteira.xp_proximo_nivel 
            porcentagem_xp = carteira.porcentagem_barra_xp
            patente = carteira.get_patente_display()
        else:
            nivel_atual = 1
            xp_atual = 0
            xp_proximo = 100
            porcentagem_xp = 0
            patente = "Sem Perfil RPG"

    except Exception:
        nivel_atual = 1
        xp_atual = 0
        xp_proximo = 100
        porcentagem_xp = 0
        patente = "Erro de Leitura"

    # ==========================================
    # 4. MURAL DE AVISOS
    # ==========================================
    avisos = ComunicadoInterno.objects.filter(ativo=True).order_by('-data_criacao')[:5]

    contexto = {
        'nome_usuario': request.user.first_name or request.user.username,
        'meus_chats': meus_chats,
        'fila_setor': fila_setor,
        'minhas_os': minhas_os,
        'os_fila_setor': os_fila_setor,
        'nivel_atual': nivel_atual,
        'xp_atual': xp_atual,
        'xp_proximo': xp_proximo,
        'porcentagem_xp': porcentagem_xp,
        'patente': patente,
        'avisos': avisos,
    }
    
    return render(request, 'home.html', contexto)