# /base_conhecimento/busca.py
"""
Busca semântica (RAG) da Base de Conhecimento.

É a função que a IA vai usar para achar o artigo certo. Combina três sinais,
na ordem que mais evita erro:

  1. ESCOPO DO CLIENTE = sistemas do cliente + sistema "Geral" (transversal).
     - Sistemas do cliente: se ele usa Clipp, busca em Clipp.
     - "Geral": base comum (assistência de PC, dúvidas genéricas, TEF...) que
       entra SEMPRE, pra todo cliente — porque um cliente do Clipp também pode
       precisar de algo de assistência técnica.

  2. BUSCA VETORIAL (significado) via pgvector (distância de cosseno).
     "nota fiscal não sai" encontra "NFC-e travada" mesmo sem repetir palavra.

  3. REFORÇO POR PALAVRA-CHAVE (título/hashtags/código) pra termos exatos.

FALLBACK SEGURO (o mais conservador):
  a) busca dentro do ESCOPO (sistemas do cliente + Geral);
  b) se achar algo confiável no escopo, retorna SÓ isso — não vaza outros
     sistemas (evita dar procedimento do sistema errado);
  c) se NÃO achar nada bom, amplia pra base toda, mas marca cada resultado
     com fora_do_sistema=True pra IA tratar como incerto.

Nada aqui altera dados. Só lê.
"""
import logging

from django.db.models import Q
from django.utils.html import strip_tags
from pgvector.django import CosineDistance

from .models import Artigo
from .embeddings import gerar_embedding, limpar_para_embedding, TASK_BUSCA

logger = logging.getLogger("rastreador_zap")

# ── Sintonia da busca ─────────────────────────────────────────────────
# CosineDistance vai de 0 (idêntico) a 2 (oposto). Textos do mesmo assunto
# ficam abaixo de ~0.35. Acima de LIMIAR_BOM: "não achou nada relevante".
LIMIAR_BOM = 0.35        # distância máxima p/ acerto "confiável" no escopo
LIMIAR_ACEITAVEL = 0.55  # acima disso, nem no modo ampliado vale mostrar
TOP_K = 4                # máximo de artigos retornados

# Sistema TRANSVERSAL somado à busca de TODO cliente. O nome precisa bater
# com o cadastrado na wiki (case-insensitive).
SISTEMA_GERAL_NOME = "Geral"


def _ids_sistema_geral():
    """IDs do(s) sistema(s) 'Geral' (lista; pode estar vazia se não existir)."""
    from sistemas.models import Sistema
    return list(
        Sistema.objects.filter(nome__iexact=SISTEMA_GERAL_NOME).values_list("pk", flat=True)
    )


def _rankear(queryset, vetor_busca, termos_texto, limite):
    """
    Aplica o ranking híbrido sobre um queryset já filtrado.
    Retorna lista de dicts: {artigo, distancia, via}.
    """
    qs = queryset.filter(embedding__isnull=False)
    qs = qs.annotate(dist=CosineDistance("embedding", vetor_busca)).order_by("dist")

    resultados = []
    vistos = set()
    for art in qs[: limite * 3]:  # excedente pra mesclar com keyword
        resultados.append({"artigo": art, "distancia": float(art.dist), "via": "significado"})
        vistos.add(art.pk)

    # reforço por palavra-chave (código de erro, sigla, nome próprio)
    if termos_texto:
        filtro_kw = Q()
        for termo in termos_texto:
            if len(termo) >= 3:
                filtro_kw |= (
                    Q(titulo__icontains=termo)
                    | Q(hashtags__icontains=termo)
                    | Q(codigo__icontains=termo)
                )
        if filtro_kw:
            for art in queryset.filter(filtro_kw)[:limite]:
                if art.pk not in vistos:
                    resultados.append({"artigo": art, "distancia": 0.40, "via": "palavra-chave"})
                    vistos.add(art.pk)

    resultados.sort(key=lambda r: r["distancia"])
    return resultados[:limite]


def buscar(pergunta_cliente, cliente=None, limite=TOP_K, api_key=None):
    """
    Busca principal. Devolve:
    {
        "resultados": [ {artigo, distancia, via, fora_do_sistema}, ... ],
        "fora_do_sistema": bool,
        "houve_filtro": bool,
        "erro": str | None,
    }
    """
    saida = {"resultados": [], "fora_do_sistema": False, "houve_filtro": False, "erro": None}

    if not pergunta_cliente or not pergunta_cliente.strip():
        saida["erro"] = "pergunta vazia"
        return saida

    vetor = gerar_embedding(pergunta_cliente, task_type=TASK_BUSCA, api_key=api_key)
    if vetor is None:
        saida["erro"] = "falha ao gerar embedding da pergunta"
        return saida

    termos = [t for t in pergunta_cliente.split() if len(t) >= 3]

    # escopo = sistemas do cliente + Geral (sempre)
    ids_escopo = set(_ids_sistema_geral())
    if cliente:
        try:
            ids_escopo.update(cliente.sistemas.values_list("pk", flat=True))
        except Exception:
            pass

    # ── Camada A: dentro do escopo ────────────────────────────────────
    if ids_escopo:
        saida["houve_filtro"] = True
        qs_escopo = Artigo.objects.filter(sistema__in=ids_escopo)
        achados = _rankear(qs_escopo, vetor, termos, limite)
        bons = [a for a in achados if a["distancia"] <= LIMIAR_BOM]
        if bons:
            for a in bons:
                a["fora_do_sistema"] = False
            saida["resultados"] = bons
            return saida

    # ── Camada B: base inteira (marca fora_do_sistema) ────────────────
    achados = _rankear(Artigo.objects.all(), vetor, termos, limite)
    achados = [a for a in achados if a["distancia"] <= LIMIAR_ACEITAVEL]
    for a in achados:
        a["fora_do_sistema"] = saida["houve_filtro"]
    saida["resultados"] = achados
    saida["fora_do_sistema"] = saida["houve_filtro"] and bool(achados)
    return saida


def formatar_para_ia(resultado_busca, max_chars_por_artigo=1200):
    """
    Transforma o resultado de buscar() no bloco de texto do prompt da IA,
    com aviso de segurança quando os artigos vieram de fora do escopo.
    """
    resultados = resultado_busca.get("resultados") or []
    if not resultados:
        return None

    partes = ["📚 BASE DE CONHECIMENTO ENCONTRADA (use se aplicável ao caso):\n"]

    if resultado_busca.get("fora_do_sistema"):
        partes.append(
            "⚠️ ATENÇÃO: não havia artigo específico do sistema deste cliente. "
            "Os resultados abaixo são de outros sistemas/base geral — podem não se "
            "aplicar. Confirme o sistema do cliente antes de aplicar qualquer passo; "
            "na dúvida, transfira para a equipe.\n"
        )

    for r in resultados:
        art = r["artigo"]
        corpo = strip_tags(limpar_para_embedding("", "", art.conteudo))
        corpo = corpo[:max_chars_por_artigo] + ("..." if len(corpo) > max_chars_por_artigo else "")
        partes.append(
            f"🔹 {art.titulo} (Cód: {art.codigo} | Sistema: {art.sistema} | "
            f"Tipo: {art.get_tipo_display()})\n{corpo}\n"
        )

    return "\n".join(partes)