import json
import random
from datetime import date, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    Carteira, Transacao,
    MissaoAtiva, ProgressoMissao,
    PasseColetivo, MarcoPasse,
    ItemColecionavel, PecaRoleta, GiroRoletaLog,
    PecaInventario, ItemInventario,
    ItemLojaOficial, ResgateLojaOficial,
    AnuncioMercado,
)
from . import utils


# ══════════════════════════════════════════════════════════════════
# PERMISSÃO DE ACESSO (mantida do sistema antigo)
# ══════════════════════════════════════════════════════════════════
def e_do_suporte(user):
    return user.is_authenticated and (
        user.groups.filter(name="Suporte Software").exists() or user.is_superuser
    )


def _ano_mes():
    return timezone.now().strftime("%Y-%m")


# ══════════════════════════════════════════════════════════════════
# 1. HUB DO JOGADOR (dashboard)
# ══════════════════════════════════════════════════════════════════
@login_required
@user_passes_test(e_do_suporte, login_url="home", redirect_field_name=None)
def dashboard(request):
    carteira, _ = Carteira.objects.get_or_create(usuario=request.user)
    hoje = timezone.now().date()

    # Missões ativas do usuário (com progresso)
    missoes = MissaoAtiva.objects.filter(
        periodo_inicio__lte=hoje, periodo_fim__gte=hoje
    ).order_by("tipo")
    missoes_por_tipo = {"DIARIA": [], "SEMANAL": [], "MENSAL": []}
    missoes_prontas = 0
    for m in missoes:
        prog, _ = ProgressoMissao.objects.get_or_create(usuario=request.user, missao=m)
        pct = min(100, int((prog.progresso_atual / m.meta_quantidade) * 100)) if m.meta_quantidade else 0
        pronta = prog.progresso_atual >= m.meta_quantidade and not prog.recompensa_resgatada
        if pronta:
            missoes_prontas += 1
        missoes_por_tipo.setdefault(m.tipo, []).append({
            "missao": m, "progresso": prog, "porcentagem": pct, "pronta": pronta,
        })

    # Passe coletivo do mês
    passe = PasseColetivo.objects.filter(ano_mes=_ano_mes(), ativo=True).first()
    marcos = list(passe.marcos.all()) if passe else []

    # Inventário
    pecas = PecaInventario.objects.filter(
        usuario=request.user, status=PecaInventario.Status.DISPONIVEL
    ).select_related("item")
    itens_completos = ItemInventario.objects.filter(
        usuario=request.user, status=ItemInventario.Status.DISPONIVEL
    ).select_related("item")

    # agrupa peças por item pra mostrar "2/6"
    inventario_pecas = {}
    for p in pecas:
        d = inventario_pecas.setdefault(p.item.id, {
            "item": p.item, "numeros": set(), "total": p.item.total_pecas
        })
        d["numeros"].add(p.numero_peca)
    for d in inventario_pecas.values():
        d["tem"] = len(d["numeros"])
        d["completo"] = d["numeros"] >= set(range(1, d["total"] + 1))

    # Loja e mercado
    itens_loja = ItemLojaOficial.objects.filter(ativo=True).order_by("preco_lc")
    anuncios = AnuncioMercado.objects.filter(
        status=AnuncioMercado.Status.ATIVO
    ).exclude(vendedor=request.user).select_related("vendedor")[:20]

    extrato = Transacao.objects.filter(carteira=carteira).order_by("-data")[:12]
    ranking = Carteira.objects.select_related("usuario").order_by("-xp_total")[:10]
    pode_resgatar_diario = carteira.ultimo_resgate_diario != date.today()

    context = {
        "carteira": carteira,
        "missoes": missoes_por_tipo,
        "missoes_prontas": missoes_prontas,
        "passe": passe, "marcos": marcos,
        "inventario_pecas": inventario_pecas.values(),
        "itens_completos": itens_completos,
        "itens_loja": itens_loja,
        "anuncios": anuncios,
        "extrato": extrato,
        "ranking": ranking,
        "pode_resgatar_diario": pode_resgatar_diario,
        "itens_colecionaveis": ItemColecionavel.objects.filter(ativo=True),
    }
    return render(request, "recompensas/dashboard.html", context)


# ══════════════════════════════════════════════════════════════════
# 2. CHECK-IN DIÁRIO (ofensiva)
# ══════════════════════════════════════════════════════════════════
@login_required
def resgate_diario(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})

    with transaction.atomic():
        carteira = Carteira.objects.select_for_update().get(usuario=request.user)
        hoje = date.today()
        ontem = hoje - timedelta(days=1)

        if carteira.ultimo_resgate_diario == hoje:
            return JsonResponse({"sucesso": False, "mensagem": "Você já fez check-in hoje!"})

        if carteira.ultimo_resgate_diario == ontem:
            carteira.ofensiva_diaria = min(carteira.ofensiva_diaria + 1, 7)
        else:
            carteira.ofensiva_diaria = 1
        carteira.maior_ofensiva = max(carteira.maior_ofensiva, carteira.ofensiva_diaria)

        # recompensa cresce com a ofensiva (dá pó, a nova moeda-mãe)
        tabela_lc = {1: 20, 2: 30, 3: 40, 4: 55, 5: 70, 6: 90, 7: 120}
        lc = tabela_lc.get(carteira.ofensiva_diaria, 20)
        xp = 15
        # a cada 7 dias seguidos, um bônus de pó
        po_bonus = 15 if carteira.ofensiva_diaria == 7 else 0

        carteira.saldo_moedas += lc
        carteira.xp_total += xp
        carteira.po_magico += po_bonus
        carteira.ultimo_resgate_diario = hoje
        utils._verificar_level_up(carteira)
        carteira.save()

        Transacao.objects.create(
            carteira=carteira, tipo=Transacao.Tipo.GANHO,
            valor_moedas=lc, valor_xp=xp,
            descricao=f"Check-in diário (ofensiva {carteira.ofensiva_diaria})"
            + (f" +{po_bonus} pó!" if po_bonus else ""),
        )

    return JsonResponse({
        "sucesso": True, "lc_ganho": lc, "xp_ganho": xp, "po_bonus": po_bonus,
        "ofensiva": carteira.ofensiva_diaria, "novo_saldo": carteira.saldo_moedas,
    })


# ══════════════════════════════════════════════════════════════════
# 3. ROLETA — gira e ganha uma PEÇA (não prêmio pronto)
# ══════════════════════════════════════════════════════════════════
@login_required
def girar_tigrinho(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})

    CUSTO_GIRO = 120

    with transaction.atomic():
        carteira = Carteira.objects.select_for_update().get(usuario=request.user)
        if carteira.saldo_moedas < CUSTO_GIRO:
            return JsonResponse({"sucesso": False, "mensagem": f"Precisa de {CUSTO_GIRO} LC para girar."})

        faces = list(PecaRoleta.objects.filter(ativo=True).select_related("item"))
        if not faces:
            return JsonResponse({"sucesso": False, "mensagem": "Roleta em manutenção."})

        carteira.saldo_moedas -= CUSTO_GIRO
        pesos = [f.peso_sorteio for f in faces]
        face = random.choices(faces, weights=pesos, k=1)[0]

        PecaInventario.objects.create(
            usuario=request.user, item=face.item, numero_peca=face.numero_peca, origem="roleta"
        )
        GiroRoletaLog.objects.create(usuario=request.user, peca=face)
        Transacao.objects.create(
            carteira=carteira, tipo=Transacao.Tipo.GASTO, valor_moedas=CUSTO_GIRO,
            descricao=f"Giro na roleta → peça {face.numero_peca} de {face.item.nome}",
        )
        carteira.save()

        raridade = face.item.raridade.lower()

    return JsonResponse({
        "sucesso": True,
        "item": face.item.nome, "peca": face.numero_peca,
        "total_pecas": face.item.total_pecas, "raridade": raridade,
        "icone": face.item.icone, "novo_saldo": carteira.saldo_moedas,
    })


# ══════════════════════════════════════════════════════════════════
# 4. PÓ MÁGICO — desencantar, craftar, montar
# ══════════════════════════════════════════════════════════════════
@login_required
def desencantar(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})
    data = json.loads(request.body or "{}")
    ok, msg, po = utils.desencantar_peca(request.user, data.get("peca_id"))
    carteira = Carteira.objects.get(usuario=request.user)
    return JsonResponse({"sucesso": ok, "mensagem": msg, "po": carteira.po_magico})


@login_required
def craftar(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})
    data = json.loads(request.body or "{}")
    ok, msg = utils.craftar_peca(request.user, data.get("item_id"), int(data.get("numero_peca", 0)))
    carteira = Carteira.objects.get(usuario=request.user)
    return JsonResponse({"sucesso": ok, "mensagem": msg, "po": carteira.po_magico})


@login_required
def montar(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})
    data = json.loads(request.body or "{}")
    ok, msg = utils.montar_item(request.user, data.get("item_id"))
    return JsonResponse({"sucesso": ok, "mensagem": msg})


# ══════════════════════════════════════════════════════════════════
# 5. LOJA OFICIAL — compra por LC
# ══════════════════════════════════════════════════════════════════
@login_required
def resgatar_item(request, item_id):
    if not e_do_suporte(request.user):
        return HttpResponseForbidden("Sem permissão.")
    if request.method != "POST":
        return redirect("recompensas:dashboard")

    with transaction.atomic():
        carteira = Carteira.objects.select_for_update().get(usuario=request.user)
        item = get_object_or_404(ItemLojaOficial, id=item_id, ativo=True)

        if item.estoque == 0:
            messages.error(request, "Item esgotado.")
            return redirect("recompensas:dashboard")

        if carteira.saldo_moedas < item.preco_lc:
            messages.error(request, "Lógica Coins insuficientes.")
            return redirect("recompensas:dashboard")

        carteira.saldo_moedas -= item.preco_lc
        carteira.save(update_fields=["saldo_moedas"])
        if item.estoque > 0:
            ItemLojaOficial.objects.filter(pk=item.pk).update(estoque=F("estoque") - 1)

        ResgateLojaOficial.objects.create(usuario=request.user, item=item, custo_pago=item.preco_lc)
        Transacao.objects.create(
            carteira=carteira, tipo=Transacao.Tipo.GASTO, valor_moedas=item.preco_lc,
            descricao=f"Loja oficial: {item.nome}",
        )
        messages.success(request, f"“{item.nome}” resgatado! Aguarde a entrega da gestão.")

    return redirect("recompensas:dashboard")


# ══════════════════════════════════════════════════════════════════
# 6. MISSÕES — resgatar recompensa de missão concluída
# ══════════════════════════════════════════════════════════════════
@login_required
def resgatar_missao(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})

    data = json.loads(request.body or "{}")
    prog_id = data.get("progresso_id")

    with transaction.atomic():
        progresso = get_object_or_404(
            ProgressoMissao.objects.select_for_update(), id=prog_id, usuario=request.user
        )
        missao = progresso.missao
        if progresso.progresso_atual < missao.meta_quantidade:
            return JsonResponse({"sucesso": False, "mensagem": "Missão ainda não concluída."})
        if progresso.recompensa_resgatada:
            return JsonResponse({"sucesso": False, "mensagem": "Recompensa já resgatada."})

        carteira = Carteira.objects.select_for_update().get(usuario=request.user)
        carteira.saldo_moedas += missao.recompensa_lc
        carteira.xp_total += missao.recompensa_xp
        utils._verificar_level_up(carteira)
        carteira.save()

        progresso.concluida = True
        progresso.recompensa_resgatada = True
        progresso.data_conclusao = timezone.now()
        progresso.save()

        Transacao.objects.create(
            carteira=carteira, tipo=Transacao.Tipo.GANHO,
            valor_moedas=missao.recompensa_lc, valor_xp=missao.recompensa_xp,
            descricao=f"Missão: {missao.titulo}",
        )

    return JsonResponse({
        "sucesso": True, "lc_ganho": missao.recompensa_lc, "xp_ganho": missao.recompensa_xp,
        "novo_saldo": carteira.saldo_moedas,
    })


# ══════════════════════════════════════════════════════════════════
# 7. MERCADO CLANDESTINO — anunciar, comprar, cancelar
# ══════════════════════════════════════════════════════════════════
@login_required
def criar_anuncio(request):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})

    data = json.loads(request.body or "{}")
    tipo = data.get("tipo")            # "ITEM" ou "PECA"
    ref_id = data.get("ref_id")        # id do ItemInventario ou PecaInventario
    preco = int(data.get("preco", 0))

    if preco <= 0:
        return JsonResponse({"sucesso": False, "mensagem": "Preço inválido."})

    with transaction.atomic():
        if tipo == "ITEM":
            inv = get_object_or_404(
                ItemInventario.objects.select_for_update(),
                id=ref_id, usuario=request.user, status=ItemInventario.Status.DISPONIVEL
            )
            inv.status = ItemInventario.Status.A_VENDA
            inv.save(update_fields=["status"])
            AnuncioMercado.objects.create(
                vendedor=request.user, tipo_conteudo="ITEM",
                item_inventario=inv, preco_lc=preco,
                descricao_venda=data.get("descricao", ""),
            )
        elif tipo == "PECA":
            # só reserva peça DISPONÍVEL — impede anunciar a mesma peça duas
            # vezes ou anunciar uma que já está à venda.
            peca = get_object_or_404(
                PecaInventario.objects.select_for_update(),
                id=ref_id, usuario=request.user,
                status=PecaInventario.Status.DISPONIVEL,
            )
            # marca como À VENDA (não remove — se algo falhar, a peça continua
            # existindo; dado nunca some).
            peca.status = PecaInventario.Status.A_VENDA
            peca.save(update_fields=["status"])
            AnuncioMercado.objects.create(
                vendedor=request.user, tipo_conteudo="PECA",
                peca_inventario=peca, preco_lc=preco,
                descricao_venda=data.get("descricao", ""),
            )
        else:
            return JsonResponse({"sucesso": False, "mensagem": "Tipo inválido."})

    return JsonResponse({"sucesso": True, "mensagem": "Anúncio criado!"})


@login_required
def comprar_anuncio(request, anuncio_id):
    if not e_do_suporte(request.user):
        return JsonResponse({"sucesso": False, "mensagem": "Acesso negado."})
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})

    with transaction.atomic():
        anuncio = get_object_or_404(
            AnuncioMercado.objects.select_for_update(),
            id=anuncio_id, status=AnuncioMercado.Status.ATIVO
        )
        if anuncio.vendedor_id == request.user.id:
            return JsonResponse({"sucesso": False, "mensagem": "Não pode comprar o próprio anúncio."})

        comprador = Carteira.objects.select_for_update().get(usuario=request.user)
        if comprador.saldo_moedas < anuncio.preco_lc:
            return JsonResponse({"sucesso": False, "mensagem": "LC insuficiente."})

        vendedor = Carteira.objects.select_for_update().get(usuario=anuncio.vendedor)

        # transfere moedas
        comprador.saldo_moedas -= anuncio.preco_lc
        vendedor.saldo_moedas += anuncio.preco_lc
        comprador.save(update_fields=["saldo_moedas"])
        vendedor.save(update_fields=["saldo_moedas"])

        # transfere o bem
        if anuncio.tipo_conteudo == "ITEM" and anuncio.item_inventario:
            inv = anuncio.item_inventario
            inv.usuario = request.user
            inv.status = ItemInventario.Status.DISPONIVEL
            inv.save(update_fields=["usuario", "status"])
        elif anuncio.tipo_conteudo == "PECA" and anuncio.peca_inventario:
            peca = anuncio.peca_inventario
            peca.usuario = request.user
            peca.origem = "mercado"
            peca.status = PecaInventario.Status.DISPONIVEL  # volta a ser usável
            peca.save(update_fields=["usuario", "origem", "status"])

        anuncio.status = AnuncioMercado.Status.VENDIDO
        anuncio.comprador = request.user
        anuncio.data_venda = timezone.now()
        anuncio.save(update_fields=["status", "comprador", "data_venda"])

        # extrato dos dois lados
        Transacao.objects.create(
            carteira=comprador, tipo=Transacao.Tipo.GASTO, valor_moedas=anuncio.preco_lc,
            descricao=f"Mercado: comprou de {anuncio.vendedor.username}",
        )
        Transacao.objects.create(
            carteira=vendedor, tipo=Transacao.Tipo.GANHO, valor_moedas=anuncio.preco_lc,
            descricao=f"Mercado: vendeu para {request.user.username}",
        )

    return JsonResponse({"sucesso": True, "mensagem": "Compra realizada!", "novo_saldo": comprador.saldo_moedas})


@login_required
def cancelar_anuncio(request, anuncio_id):
    if request.method != "POST":
        return JsonResponse({"sucesso": False, "mensagem": "Método inválido."})
    with transaction.atomic():
        anuncio = get_object_or_404(
            AnuncioMercado.objects.select_for_update(),
            id=anuncio_id, vendedor=request.user, status=AnuncioMercado.Status.ATIVO
        )
        # devolve o bem ao status disponível (item OU peça)
        if anuncio.tipo_conteudo == "ITEM" and anuncio.item_inventario:
            anuncio.item_inventario.status = ItemInventario.Status.DISPONIVEL
            anuncio.item_inventario.save(update_fields=["status"])
        elif anuncio.tipo_conteudo == "PECA" and anuncio.peca_inventario:
            anuncio.peca_inventario.status = PecaInventario.Status.DISPONIVEL
            anuncio.peca_inventario.save(update_fields=["status"])
        anuncio.status = AnuncioMercado.Status.CANCELADO
        anuncio.save(update_fields=["status"])
    return JsonResponse({"sucesso": True, "mensagem": "Anúncio cancelado."})