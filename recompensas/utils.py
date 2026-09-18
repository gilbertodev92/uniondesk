"""
MOTOR DE GAMIFICAÇÃO — recompensas/utils.py

Reescrito para o sistema RPG novo. Mudanças-chave em relação ao antigo:

  1. RENDIMENTO DECRESCENTE (o coração do balanceamento):
     repetir a MESMA ação no mês faz cada repetição render menos.
     Isso substitui a "trava por segundo" antiga (que só atrasava o farm):
     agora farmar a mesma coisa simplesmente rende cada vez menos, o que
     empurra a pessoa a variar e ajudar o colega.

  2. PUNIÇÕES SUAVES: a avaliação 1 estrela deixava a pessoa -2000 LC / -1000 XP
     (destruía semanas). Agora é um toque simbólico, não um cataclismo.

  3. INTEGRAÇÃO COM MISSÕES: cada ação avança as missões ativas que usam
     aquele gatilho, e alimenta o passe coletivo da equipe.

A ASSINATURA PÚBLICA NÃO MUDA:
    processar_acao_gamificada(usuario, acao, detalhe="")
Todos os outros módulos (atendimentos, cs, wiki, arquivos, whatsapp_bot...)
continuam chamando exatamente igual. Nada quebra.
"""
import logging
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Carteira, Transacao, ContadorAcaoMensal,
    MissaoAtiva, ProgressoMissao, PasseColetivo, MarcoPasse,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# REGRAS BASE — o ganho CHEIO de cada ação (antes do rendimento decrescente)
# ══════════════════════════════════════════════════════════════════
# Valores base equilibrados: nada de "CS vale 200". A diferença entre ações
# agora é pequena; o que separa quem se dedica é o VOLUME e a VARIEDADE,
# suavizados pelo rendimento decrescente. Ajuste fino no futuro, se quiser.
REGRAS = {
    # ação                        xp   lc   descrição              pontos p/ passe coletivo
    'fechar_chamado':            {'xp': 10, 'lc': 5,  'desc': 'Atendimento finalizado',      'passe': 3},
    'atualizar_chamado':         {'xp': 3,  'lc': 1,  'desc': 'Interação em atendimento',    'passe': 1},
    'finalizar_chat':            {'xp': 8,  'lc': 4,  'desc': 'Chat (bot) finalizado',       'passe': 2},
    'finalizar_grupo':           {'xp': 9,  'lc': 4,  'desc': 'Atendimento de grupo',        'passe': 2},
    'responder_grupo':           {'xp': 5,  'lc': 2,  'desc': 'Resposta em grupo',           'passe': 1},
    'registrar_contato_cs':      {'xp': 12, 'lc': 6,  'desc': 'Follow-up de CS',             'passe': 3},
    'feedback_5_estrelas':       {'xp': 25, 'lc': 12, 'desc': 'Avaliação 5 estrelas',        'passe': 5},
    'cadastrar_base_conhecimento':{'xp': 8, 'lc': 5,  'desc': 'Novo artigo na base',         'passe': 2},
    'subir_arquivo':             {'xp': 6,  'lc': 3,  'desc': 'Upload de instalador',        'passe': 1},
    'criar_evento_agenda':       {'xp': 5,  'lc': 2,  'desc': 'Evento na agenda',            'passe': 1},
    'cadastrar_cliente':         {'xp': 6,  'lc': 4,  'desc': 'Novo cliente cadastrado',     'passe': 1},
    'vincular_cliente':          {'xp': 5,  'lc': 3,  'desc': 'Cliente vinculado',           'passe': 1},

    # PUNIÇÕES SUAVES (o "chicote" virou um "toque no ombro")
    'feedback_1_estrela':        {'xp': -30,  'lc': -40, 'desc': 'Avaliação 1 estrela',      'passe': 0},
    'feedback_2_estrelas':       {'xp': -20,  'lc': -25, 'desc': 'Avaliação 2 estrelas',     'passe': 0},
    'feedback_3_estrelas':       {'xp': -5,   'lc': -8,  'desc': 'Avaliação 3 estrelas',     'passe': 0},
    'chamado_atrasado':          {'xp': -8,   'lc': -10, 'desc': 'SLA estourado',            'passe': 0},
    'chat_abandonado':           {'xp': -8,   'lc': -8,  'desc': 'Chat abandonado na fila',  'passe': 0},
    'reclamacao_direta':         {'xp': -25,  'lc': -40, 'desc': 'Reclamação direta',        'passe': 0},
}

# Sinônimos legados que outros módulos ainda possam mandar → mapeia pro nome oficial
SINONIMOS = {
    'Receber Feedback 5 Estrelas': 'feedback_5_estrelas',
    'Finalizar Chat no WhatsApp': 'finalizar_chat',
    'finalizar_chat_whatsapp': 'finalizar_chat',
}


# ══════════════════════════════════════════════════════════════════
# RENDIMENTO DECRESCENTE
# ══════════════════════════════════════════════════════════════════
# Retorna o MULTIPLICADOR (0.2 a 1.0) conforme quantas vezes o usuário já
# fez esta ação no mês. Quanto mais repete, menos rende — piso de 20%.
#
#   1ª–5ª vez  : 100%
#   6ª–15ª     : ~70–90% (decai suave)
#   16ª–40ª    : ~40–70%
#   41ª+       : piso 20%
#
# A curva é suave (não é degrau), então nunca "trava" de repente.
def _multiplicador_rendimento(quantidade_ja_feita):
    n = quantidade_ja_feita
    if n < 5:
        return 1.0
    if n >= 60:
        return 0.20
    # decai linearmente de 1.0 (em n=5) até 0.20 (em n=60)
    fator = 1.0 - ((n - 5) / 55) * 0.8
    return round(max(fator, 0.20), 2)


def _ano_mes_atual():
    return timezone.now().strftime("%Y-%m")


# ══════════════════════════════════════════════════════════════════
# FUNÇÃO PÚBLICA — a mesma assinatura de sempre
# ══════════════════════════════════════════════════════════════════
def processar_acao_gamificada(usuario, acao, detalhe=""):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return False

    acao = SINONIMOS.get(acao, acao)
    regra = REGRAS.get(acao)
    if not regra:
        return False

    is_punicao = regra['xp'] < 0 or regra['lc'] < 0

    try:
        with transaction.atomic():
            carteira, _ = Carteira.objects.select_for_update().get_or_create(usuario=usuario)

            if is_punicao:
                # punição: valor cheio, sem rendimento decrescente, sem missão
                xp_ganho = regra['xp']
                lc_ganho = regra['lc']
                mult = 1.0
            else:
                # ganho: aplica rendimento decrescente do mês
                ano_mes = _ano_mes_atual()
                contador, _ = ContadorAcaoMensal.objects.select_for_update().get_or_create(
                    usuario=usuario, acao=acao, ano_mes=ano_mes
                )
                mult = _multiplicador_rendimento(contador.quantidade)
                xp_ganho = max(int(regra['xp'] * mult), 1)   # sempre ganha ao menos 1
                lc_ganho = max(int(regra['lc'] * mult), 1)
                contador.quantidade = F('quantidade') + 1
                contador.save(update_fields=['quantidade'])

            # aplica na carteira
            carteira.xp_total = max(carteira.xp_total + xp_ganho, 0)
            carteira.saldo_moedas = max(carteira.saldo_moedas + lc_ganho, 0)
            if not is_punicao:
                _verificar_level_up(carteira)
            carteira.save(update_fields=['xp_total', 'saldo_moedas', 'nivel_atual'])

            # extrato
            desc = regra['desc'] + (f" ({detalhe})" if detalhe else "")
            if not is_punicao and mult < 1.0:
                desc += f" · rendimento {int(mult*100)}%"
            Transacao.objects.create(
                carteira=carteira,
                tipo=Transacao.Tipo.GANHO if not is_punicao else Transacao.Tipo.GASTO,
                valor_moedas=abs(lc_ganho),
                valor_xp=abs(xp_ganho),
                descricao=desc,
            )

            if not is_punicao:
                _avancar_missoes(usuario, acao)
                _avancar_passe_coletivo(regra.get('passe', 0))

        return True

    except Exception as e:
        logger.error(f"Erro na gamificação ({acao}) de {usuario}: {e}")
        return False


def _verificar_level_up(carteira):
    novo_nivel = int((carteira.xp_total / 100) ** 0.5) + 1
    if novo_nivel > carteira.nivel_atual:
        carteira.nivel_atual = novo_nivel
        return True
    return False


# ══════════════════════════════════════════════════════════════════
# MISSÕES — avança o progresso das missões ativas que usam este gatilho
# ══════════════════════════════════════════════════════════════════
def _avancar_missoes(usuario, gatilho):
    hoje = timezone.now().date()
    missoes = MissaoAtiva.objects.filter(
        gatilho=gatilho, periodo_inicio__lte=hoje, periodo_fim__gte=hoje
    )
    for missao in missoes:
        prog, _ = ProgressoMissao.objects.get_or_create(usuario=usuario, missao=missao)
        if prog.concluida:
            continue
        prog.progresso_atual = F('progresso_atual') + 1
        prog.save(update_fields=['progresso_atual'])
        prog.refresh_from_db()
        if prog.progresso_atual >= missao.meta_quantidade:
            prog.concluida = True
            prog.data_conclusao = timezone.now()
            prog.save(update_fields=['concluida', 'data_conclusao'])


# ══════════════════════════════════════════════════════════════════
# PASSE COLETIVO — soma pontos no balde da equipe e checa marcos
# ══════════════════════════════════════════════════════════════════
def _avancar_passe_coletivo(pontos):
    if pontos <= 0:
        return
    ano_mes = _ano_mes_atual()
    passe, _ = PasseColetivo.objects.get_or_create(ano_mes=ano_mes)
    PasseColetivo.objects.filter(pk=passe.pk).update(pontos_atuais=F('pontos_atuais') + pontos)
    passe.refresh_from_db()
    # marca marcos recém-atingidos (a entrega da recompensa é manual pela gestão)
    for marco in passe.marcos.filter(atingido=False, pontos_necessarios__lte=passe.pontos_atuais):
        marco.atingido = True
        marco.data_atingido = timezone.now()
        marco.save(update_fields=['atingido', 'data_atingido'])
        logger.info(f"🎉 Passe coletivo {ano_mes}: marco '{marco.recompensa_titulo}' atingido!")


# ══════════════════════════════════════════════════════════════════
# PÓ MÁGICO — desencantar e craftar
# ══════════════════════════════════════════════════════════════════
from .models import ItemColecionavel, PecaInventario, ItemInventario


def desencantar_peca(usuario, peca_inventario_id):
    """
    Destrói uma peça do inventário e devolve pó mágico (conforme a raridade
    do item). Retorna (ok, mensagem, po_ganho).
    """
    try:
        with transaction.atomic():
            peca = PecaInventario.objects.select_for_update().get(
                id=peca_inventario_id, usuario=usuario
            )
            # não deixa desencantar peça que está anunciada no mercado
            if peca.status == PecaInventario.Status.A_VENDA:
                return False, "Esta peça está à venda no mercado. Cancele o anúncio antes.", 0
            item = peca.item
            po = item.po_ao_desencantar

            carteira = Carteira.objects.select_for_update().get(usuario=usuario)
            # atribuição direta (não F()) porque logo abaixo criamos uma
            # Transacao usando 'carteira' — com F() pendente o objeto fica
            # "sujo" e o valor não estaria resolvido.
            carteira.po_magico = (carteira.po_magico or 0) + po
            carteira.save(update_fields=['po_magico'])

            peca.delete()

            Transacao.objects.create(
                carteira=carteira, tipo=Transacao.Tipo.GANHO,
                valor_moedas=0, valor_xp=0,
                descricao=f"Desencantou peça de {item.nome} → +{po} pó",
            )
            return True, f"+{po} pó mágico de {item.nome}", po
    except PecaInventario.DoesNotExist:
        return False, "Peça não encontrada no seu inventário.", 0
    except Exception as e:
        logger.error(f"Erro ao desencantar ({usuario}): {e}")
        return False, "Erro ao desencantar.", 0


def craftar_peca(usuario, item_id, numero_peca):
    """
    Gasta pó mágico para fabricar uma peça específica de um item.
    Retorna (ok, mensagem).
    """
    try:
        with transaction.atomic():
            item = ItemColecionavel.objects.get(id=item_id, ativo=True)

            if numero_peca < 1 or numero_peca > item.total_pecas:
                return False, "Número de peça inválido."

            carteira = Carteira.objects.select_for_update().get(usuario=usuario)
            custo = item.po_para_craftar

            if carteira.po_magico < custo:
                return False, f"Pó insuficiente. Precisa de {custo}, você tem {carteira.po_magico}."

            carteira.po_magico = (carteira.po_magico or 0) - custo
            carteira.save(update_fields=['po_magico'])

            PecaInventario.objects.create(
                usuario=usuario, item=item, numero_peca=numero_peca,
                origem="craft", status=PecaInventario.Status.DISPONIVEL,
            )
            Transacao.objects.create(
                carteira=carteira, tipo=Transacao.Tipo.GASTO,
                valor_moedas=0, valor_xp=0,
                descricao=f"Craftou peça {numero_peca} de {item.nome} → -{custo} pó",
            )
            return True, f"Peça {numero_peca} de {item.nome} craftada!"
    except ItemColecionavel.DoesNotExist:
        return False, "Item não encontrado."
    except Carteira.DoesNotExist:
        return False, "Carteira não encontrada."
    except Exception as e:
        logger.error(f"Erro ao craftar ({usuario}): {e}")
        return False, "Erro ao craftar."


def montar_item(usuario, item_id):
    """
    Se o usuário tem TODAS as peças de um item, consome as peças e cria o
    item completo no inventário. Retorna (ok, mensagem).
    """
    try:
        with transaction.atomic():
            item = ItemColecionavel.objects.get(id=item_id)
            # só peças DISPONÍVEIS entram na montagem — as que estão à venda
            # no mercado ficam de fora até o anúncio ser cancelado/vendido.
            pecas = PecaInventario.objects.select_for_update().filter(
                usuario=usuario, item=item, status=PecaInventario.Status.DISPONIVEL
            )
            numeros = set(p.numero_peca for p in pecas)
            necessarios = set(range(1, item.total_pecas + 1))

            if not necessarios.issubset(numeros):
                faltam = necessarios - numeros
                return False, f"Faltam peças: {sorted(faltam)}"

            # consome UMA de cada número (caso tenha duplicadas, sobra pro desencante)
            for n in necessarios:
                p = pecas.filter(numero_peca=n).first()
                p.delete()

            ItemInventario.objects.create(
                usuario=usuario, item=item, nome_snapshot=item.nome,
                status=ItemInventario.Status.DISPONIVEL,
            )
            return True, f"{item.nome} montado! Confira seu inventário."
    except ItemColecionavel.DoesNotExist:
        return False, "Item não encontrado."
    except Exception as e:
        logger.error(f"Erro ao montar ({usuario}): {e}")
        return False, "Erro ao montar item."