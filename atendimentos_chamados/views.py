import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, When, IntegerField, Q
from django.http import JsonResponse
from django.contrib import messages
from .models import Atendimento, Setor, AtendimentoHistorico
from .forms import AtendimentoForm
from clientes_sistemas.models import Cliente

# === GATILHO DA GAMIFICAÇÃO (IMPORTADO DO NOSSO CÉREBRO) ===
from recompensas.utils import processar_acao_gamificada

User = get_user_model()

def usuario_tem_permissao_setor(user, atendimento):
    """
    Trava de Segurança: Verifica se o usuário pode mexer no atendimento.
    """
    # 1. Administradores/Gerência sempre podem tudo
    if user.is_superuser or user.groups.filter(name__in=['Admins', 'Irrestrito', 'Gerencia', 'Gerente']).exists():
        return True
        
    # 2. Se o atendimento está "solto" (Sem Setor / Triagem), qualquer um pode puxar
    if not atendimento.setor_atual:
        return True
        
    # 3. Se o usuário já é o técnico responsável, ele pode alterar
    if atendimento.tecnico_responsavel == user:
        return True
        
    # 4. Compara o nome do Setor do atendimento com os Grupos do Usuário
    nome_setor_ticket = str(atendimento.setor_atual.nome).lower()
    for grupo in user.groups.all():
        nome_grupo = str(grupo.name).lower()
        if nome_setor_ticket in nome_grupo or nome_grupo in nome_setor_ticket:
            return True
            
    # 5. Caso use campo de setor direto no User (Fallback)
    if hasattr(user, 'setor') and getattr(user, 'setor'):
        if str(user.setor).lower() in nome_setor_ticket:
            return True
            
    return False

# ============================
# AUTOCOMPLETE CLIENTE
# ============================
@login_required
def autocomplete_cliente(request):
    termo = request.GET.get("q", "").strip()

    # Busca por nome OU por CNPJ. Como o CNPJ é salvo com máscara
    # (00.000.000/0000-00), comparamos também só os dígitos do que foi digitado
    # contra os dígitos do CNPJ, para achar mesmo quem digita sem pontuação.
    termo_numeros = re.sub(r"\D", "", termo)

    filtro = Q(razao_social__icontains=termo) | Q(cnpj__icontains=termo)
    if termo_numeros:
        filtro |= Q(cnpj__icontains=termo_numeros)

    clientes = Cliente.objects.filter(filtro).order_by("razao_social")[:15]

    resultados = [
        {"id": c.codigo, "nome": f"{c.razao_social} - {c.cnpj}"}
        for c in clientes
    ]
    return JsonResponse(resultados, safe=False)


# ============================
# LISTAR ATENDIMENTOS (MODO KANBAN / NÍVEL NASA)
# ============================
@login_required
def listar_atendimentos(request):

    busca = request.GET.get("busca", "")
    tecnico = request.GET.get("tecnico", "")
    prioridade = request.GET.get("prioridade", "")
    status = request.GET.get("status", "")
    mostrar_concluidos = request.GET.get("concluidos")

    cliente_novo = request.GET.get("cliente_novo")
    modulo_novo = request.GET.get("modulo_novo")
    treinamento = request.GET.get("treinamento")

    atendimentos = Atendimento.objects.select_related(
        "cliente",
        "setor_atual",
        "tecnico_responsavel"
    ).all()

    # Filtros
    if busca:
        atendimentos = atendimentos.filter(
            Q(titulo__icontains=busca) |
            Q(cliente__razao_social__icontains=busca)
        )
    if tecnico:
        atendimentos = atendimentos.filter(tecnico_responsavel_id=tecnico)
    if prioridade:
        atendimentos = atendimentos.filter(prioridade=prioridade)
    if status:
        atendimentos = atendimentos.filter(status=status)
    if not mostrar_concluidos:
        atendimentos = atendimentos.exclude(status=Atendimento.Status.CONCLUIDO)
    if cliente_novo:
        atendimentos = atendimentos.filter(implantacao_cliente_novo=True)
    if modulo_novo:
        atendimentos = atendimentos.filter(implantacao_modulo_novo=True)
    if treinamento:
        atendimentos = atendimentos.filter(possui_treinamento=True)

    # Ordenação de prioridade dentro do quadro
    atendimentos = atendimentos.annotate(
        prioridade_ordem=Case(
            When(prioridade="CRITICA", then=0),
            When(prioridade="ALTA", then=1),
            When(prioridade="MEDIA", then=2),
            When(prioridade="BAIXA", then=3),
            output_field=IntegerField(),
        )
    ).order_by("prioridade_ordem", "-data_abertura")

    # =================================================================
    # AGRUPAMENTO POR SETOR PARA GERAR AS COLUNAS (KANBAN)
    # Cada coluna guarda o próprio objeto Setor (com id) para o
    # drag-and-drop saber para qual setor transferir. A "Triagem" é a
    # fila dos que estão sem setor (setor_atual = None) e vem primeiro.
    # =================================================================
    TRIAGEM = "Fila de Triagem / Sem Setor"
    grupos = {}  # nome -> {"setor": obj|None, "tickets": [...]}
    for a in atendimentos:
        if a.setor_atual:
            chave = a.setor_atual.nome
            grupos.setdefault(chave, {"setor": a.setor_atual, "tickets": []})
        else:
            chave = TRIAGEM
            grupos.setdefault(chave, {"setor": None, "tickets": []})
        grupos[chave]["tickets"].append(a)

    # Garante que TODOS os setores ativos apareçam como coluna, mesmo vazios,
    # para dar destino ao arrastar (antes, setor sem card não virava coluna).
    for s in Setor.objects.filter(ativo=True):
        grupos.setdefault(s.nome, {"setor": s, "tickets": []})

    nomes = sorted(grupos.keys())
    if TRIAGEM in nomes:
        nomes.remove(TRIAGEM)
        nomes.insert(0, TRIAGEM)

    # kanban_data: lista de (nome, setor_obj_ou_None, tickets)
    kanban_data = [(nome, grupos[nome]["setor"], grupos[nome]["tickets"]) for nome in nomes]

    # Contagens dos badges numa passada só (em vez de 3 COUNT separados)
    from collections import Counter
    contagem = Counter(
        Atendimento.objects.values_list("status", flat=True)
    )
    total_abertos = contagem.get(Atendimento.Status.ABERTO, 0)
    total_em_atendimento = contagem.get(Atendimento.Status.EM_ATENDIMENTO, 0)
    total_criticos = Atendimento.objects.filter(prioridade="CRITICA").count()

    context = {
        "kanban_data": kanban_data,
        "total_geral": len(atendimentos),
        "tecnicos": User.objects.filter(is_active=True),
        "prioridades": Atendimento.Prioridade.choices,
        "status_list": Atendimento.Status.choices,
        "cliente_novo": cliente_novo,
        "modulo_novo": modulo_novo,
        "treinamento": treinamento,
        "total_abertos": total_abertos,
        "total_em_atendimento": total_em_atendimento,
        "total_criticos": total_criticos,
        "setores": Setor.objects.filter(ativo=True),
    }

    return render(request, "atendimentos_chamados/listar.html", context)

# ============================
# CRIAR ATENDIMENTO
# ============================
@login_required
def criar_atendimento(request):
    if request.method == "POST":
        form = AtendimentoForm(request.POST)

        if form.is_valid():
            atendimento = form.save(commit=False)
            cliente_id = request.POST.get("cliente")
            if cliente_id:
                atendimento.cliente = get_object_or_404(Cliente, pk=cliente_id)

            atendimento.save()

            AtendimentoHistorico.objects.create(
                atendimento=atendimento,
                usuario=request.user,
                setor=atendimento.setor_atual,
                comentario="Chamado criado"
            )

            return redirect("atendimentos_chamados:listar")
    else:
        form = AtendimentoForm()

    return render(request, "atendimentos_chamados/criar.html", {"form": form})


# ============================
# DETALHE ATENDIMENTO (ONDE A MAGIA ACONTECE)
# ============================
@login_required
def detalhe_atendimento(request, numero):
    atendimento = get_object_or_404(Atendimento, numero=numero)

    if request.method == "POST":
        # 🔥 TRAVA DE SEGURANÇA: Bloqueia se for de outro setor
        if not usuario_tem_permissao_setor(request.user, atendimento):
            messages.error(request, "⛔ Acesso Negado: Você não tem permissão para alterar um atendimento que pertence a outro setor.")
            return redirect("atendimentos_chamados:detalhe", numero=numero)
            
        # 1. Verifica se é o formulário de NOVO COMENTÁRIO
        acao = request.POST.get("acao")
        if acao == "comentario":
            texto_comentario = request.POST.get("comentario")
            if texto_comentario:
                AtendimentoHistorico.objects.create(
                    atendimento=atendimento,
                    usuario=request.user,
                    setor=atendimento.setor_atual,
                    comentario=texto_comentario
                )
                
                # ---> GAMIFICAÇÃO: Ganha XP de interação
                processar_acao_gamificada(request.user, 'atualizar_chamado', f"Comentou na OS #{numero}")

            return redirect("atendimentos_chamados:detalhe", numero=numero)

        # 2. Verifica se é a ação rápida de ENCERRAR CHAMADO
        if acao == "encerrar":
            atendimento.status = Atendimento.Status.CONCLUIDO
            atendimento.save()
            AtendimentoHistorico.objects.create(
                atendimento=atendimento,
                usuario=request.user,
                setor=atendimento.setor_atual,
                comentario="Chamado Encerrado via ação rápida."
            )
            
            # ---> GAMIFICAÇÃO: Recompensa máxima (Fechou o chamado)
            processar_acao_gamificada(request.user, 'fechar_chamado', f"Encerrou a OS #{numero}")

            return redirect("atendimentos_chamados:detalhe", numero=numero)

        # 3. Lógica do PAINEL DE CONTROLE (Alterar Status/Tecnico/Prioridade)
        status_antigo = atendimento.status
        prioridade_antiga = atendimento.prioridade
        tecnico_antigo = atendimento.tecnico_responsavel
        setor_antigo = atendimento.setor_atual

        novo_status = request.POST.get("status")
        nova_prioridade = request.POST.get("prioridade")
        novo_tecnico_id = request.POST.get("tecnico")
        novo_setor_id = request.POST.get("setor")

        alteracoes = []

        if novo_status and novo_status != status_antigo:
            atendimento.status = novo_status
            alteracoes.append(f"Status: {atendimento.get_status_display()}")

        if nova_prioridade and nova_prioridade != prioridade_antiga:
            atendimento.prioridade = nova_prioridade
            alteracoes.append(f"Prioridade: {atendimento.get_prioridade_display()}")

        if novo_tecnico_id:
            novo_tecnico = User.objects.get(id=novo_tecnico_id)
            if novo_tecnico != tecnico_antigo:
                atendimento.tecnico_responsavel = novo_tecnico
                alteracoes.append(f"Técnico: {novo_tecnico.username}")

        if novo_setor_id:
            novo_setor = Setor.objects.get(id=novo_setor_id)
            if novo_setor != setor_antigo:
                atendimento.setor_atual = novo_setor
                alteracoes.append(f"Setor: {novo_setor.nome}")

        if alteracoes:
            atendimento.save()
            AtendimentoHistorico.objects.create(
                atendimento=atendimento,
                usuario=request.user,
                setor=atendimento.setor_atual,
                comentario=" | ".join(alteracoes)
            )
            
            # ---> GAMIFICAÇÃO: Se a alteração foi concluir, dá o bônus máximo. Se não, dá bônus de interação.
            if novo_status == Atendimento.Status.CONCLUIDO and status_antigo != Atendimento.Status.CONCLUIDO:
                processar_acao_gamificada(request.user, 'fechar_chamado', f"Painel: Concluiu OS #{numero}")
            else:
                processar_acao_gamificada(request.user, 'atualizar_chamado', f"Painel: Atualizou OS #{numero}")

        return redirect("atendimentos_chamados:detalhe", numero=numero)

    historico = AtendimentoHistorico.objects.filter(
        atendimento=atendimento
    ).select_related("usuario", "setor").order_by("-data")

    return render(request, "atendimentos_chamados/detalhe.html", {
        "atendimento": atendimento,
        "historico": historico,
        "tecnicos": User.objects.all(),
        "status_list": Atendimento.Status.choices,
        "prioridades": Atendimento.Prioridade.choices,
        "setores": Setor.objects.filter(ativo=True),
        "pode_editar": usuario_tem_permissao_setor(request.user, atendimento), # 🔥 Manda pro HTML
    })


# ============================
# ENVIAR PARA SETOR
# ============================
@login_required
def enviar_para_setor(request, numero):
    atendimento = get_object_or_404(Atendimento, numero=numero)

    if request.method == "POST":
        # 🔥 TRAVA DE SEGURANÇA
        if not usuario_tem_permissao_setor(request.user, atendimento):
            messages.error(request, "⛔ Acesso Negado: Você não pode transferir um atendimento de um setor que não é o seu.")
            return redirect("atendimentos_chamados:detalhe", numero=numero)

        setor_id = request.POST.get("setor")

        if setor_id:
            novo_setor = get_object_or_404(Setor, id=setor_id)

            atendimento.setor_atual = novo_setor
            atendimento.status = Atendimento.Status.EM_ATENDIMENTO
            atendimento.save()

            AtendimentoHistorico.objects.create(
                atendimento=atendimento,
                usuario=request.user,
                setor=novo_setor,
                comentario=f"Chamado enviado para setor {novo_setor.nome}"
            )
            
            # ---> GAMIFICAÇÃO: Interação
            processar_acao_gamificada(request.user, 'atualizar_chamado', f"OS #{numero} transferida para {novo_setor.nome}")

    return redirect("atendimentos_chamados:detalhe", numero=numero)

# ============================
# TÉCNICOS DE UM SETOR (para o modal do drag-and-drop)
# ============================
@login_required
def tecnicos_do_setor(request, setor_id):
    """
    Devolve os usuários que pertencem a um setor, para o modal de transferência
    do Kanban escolher quem recebe. Usa o mesmo critério do
    usuario_tem_permissao_setor: grupos cujo nome bate com o nome do setor.
    """
    setor = get_object_or_404(Setor, id=setor_id)
    nome_setor = str(setor.nome).lower()

    usuarios = []
    for u in User.objects.filter(is_active=True).prefetch_related("groups"):
        for g in u.groups.all():
            ng = str(g.name).lower()
            if nome_setor in ng or ng in nome_setor:
                usuarios.append(u)
                break

    # fallback: se nenhum grupo casa com o setor, oferece todos os ativos
    # (melhor deixar escolher do que travar a transferência)
    if not usuarios:
        usuarios = list(User.objects.filter(is_active=True))

    dados = [
        {"id": u.id, "nome": (u.get_full_name() or u.username)}
        for u in usuarios
    ]
    return JsonResponse(dados, safe=False)


# ============================
# TRANSFERIR (usado pelo drag-and-drop do Kanban)
# ============================
@login_required
def transferir_atendimento(request, numero):
    """
    Move o atendimento para outro setor E (opcionalmente) já define o técnico
    responsável — tudo numa ação, como o usuário pediz ao arrastar o card.

    Atômico: usa select_for_update para dois usuários não se atropelarem
    transferindo o mesmo card ao mesmo tempo.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "erro": "Método inválido"}, status=405)

    setor_id = request.POST.get("setor_id")
    tecnico_id = request.POST.get("tecnico_id") or None

    try:
        with transaction.atomic():
            atendimento = Atendimento.objects.select_for_update().get(numero=numero)

            # mesma trava de permissão do resto do módulo
            if not usuario_tem_permissao_setor(request.user, atendimento):
                return JsonResponse(
                    {"ok": False, "erro": "Você não tem permissão para transferir este atendimento."},
                    status=403,
                )

            novo_setor = get_object_or_404(Setor, id=setor_id)
            partes = [f"Setor: {novo_setor.nome}"]
            atendimento.setor_atual = novo_setor

            if tecnico_id:
                novo_tecnico = get_object_or_404(User, id=tecnico_id)
                atendimento.tecnico_responsavel = novo_tecnico
                partes.append(f"Responsável: {novo_tecnico.get_full_name() or novo_tecnico.username}")

            # ao entrar num setor, sai de 'Aberto' para 'Em atendimento'
            if atendimento.status == Atendimento.Status.ABERTO:
                atendimento.status = Atendimento.Status.EM_ATENDIMENTO

            atendimento.save()

            AtendimentoHistorico.objects.create(
                atendimento=atendimento,
                usuario=request.user,
                setor=novo_setor,
                comentario="Transferência via quadro — " + " | ".join(partes),
            )

        processar_acao_gamificada(
            request.user, "atualizar_chamado", f"Transferiu atendimento #{numero}"
        )
        return JsonResponse({"ok": True})

    except Atendimento.DoesNotExist:
        return JsonResponse({"ok": False, "erro": "Atendimento não encontrado"}, status=404)


# ============================
# GERAR PDF (CHECKLIST A4)
# ============================
@login_required
def resumo_implantacao_pdf(request, numero):
    atendimento = get_object_or_404(Atendimento, numero=numero)
    return render(request, "atendimentos_chamados/resumo_print.html", {"atendimento": atendimento})