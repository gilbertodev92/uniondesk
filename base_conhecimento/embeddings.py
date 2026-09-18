# /base_conhecimento/embeddings.py
"""
Camada de embeddings (vetores semânticos) da Base de Conhecimento.

Este módulo é a ÚNICA porta de entrada para gerar vetores. Tanto o comando
de indexação quanto a busca da IA passam por aqui — assim o modelo, a
dimensão e a limpeza de texto ficam definidos num lugar só.

Regras de ouro:
  * NUNCA levanta exceção pra fora sem tratamento: falha vira `None`, e quem
    chama decide o que fazer (pular o artigo, logar, etc.). Indexação que
    derruba com um artigo problemático é pior que indexação incompleta.
  * A chave do Gemini vem do MESMO lugar que o bot usa: BotConfig no banco.
  * O texto é limpo de HTML e de imagens base64 ANTES de virar vetor — senão
    o vetor representaria "ruído de screenshot", não o assunto do artigo.
"""
import logging
import re

from django.utils.html import strip_tags

logger = logging.getLogger("rastreador_zap")

# ── Configuração do modelo ────────────────────────────────────────────
# gemini-embedding-001 é o modelo atual (o text-embedding-004 foi
# descontinuado). Ele gera 3072 dims por padrão, mas pedimos 768 via
# output_dimensionality pra bater com a coluna VectorField(768) já criada.
# Se trocar EMBED_DIM, ajuste o dimensions= no models.py e reindexe TUDO.
EMBED_MODEL = "models/gemini-embedding-001"
EMBED_DIM = 768

# task_type melhora MUITO a qualidade: o Gemini gera vetores diferentes para
# "isto é um documento a ser guardado" vs "isto é uma pergunta de busca".
TASK_DOCUMENTO = "retrieval_document"   # ao indexar artigos
TASK_BUSCA = "retrieval_query"          # ao buscar com a dúvida do cliente


# ══════════════════════════════════════════════════════════════════════
# CHAVE DA API (mesma fonte do bot)
# ══════════════════════════════════════════════════════════════════════
def _get_api_key():
    """Lê a chave Gemini do BotConfig — a mesma que o whatsapp_bot usa."""
    try:
        from whatsapp_bot.models import BotConfig
        config = BotConfig.objects.first()
        if config and config.chave_api_gemini:
            return config.chave_api_gemini.strip()
    except Exception as e:
        logger.error(f"[EMBED] Não consegui ler a chave do BotConfig: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════
# LIMPEZA DE TEXTO
# ══════════════════════════════════════════════════════════════════════
# Os artigos guardam screenshots como data:image/...;base64,<centenas de KB>.
# Isso precisa sumir antes de gerar o vetor: é ruído puro e estoura o limite
# de tamanho da API. Também tiramos tags HTML e espaços redundantes.
RE_DATA_URI = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+", re.IGNORECASE)
RE_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
RE_ESPACOS = re.compile(r"\s+")

# Limite defensivo de caracteres enviados à API (bem abaixo do teto do modelo).
# 8000 chars cobrem com folga qualquer artigo real de suporte.
MAX_CHARS = 8000


def limpar_para_embedding(titulo: str, hashtags: str, conteudo_html: str) -> str:
    """
    Monta o texto que representa o artigo para fins de busca.

    Inclui título e hashtags junto do corpo: eles carregam muito significado
    e ajudam o vetor a "entender" o assunto mesmo em artigos curtos.
    """
    # 1) mata as imagens embutidas ANTES de qualquer coisa
    corpo = RE_IMG_TAG.sub(" ", conteudo_html or "")
    corpo = RE_DATA_URI.sub(" ", corpo)
    # 2) tira o restante do HTML
    corpo = strip_tags(corpo)
    # 3) normaliza entidades e espaços
    corpo = corpo.replace("&nbsp;", " ").replace("\xa0", " ")
    corpo = RE_ESPACOS.sub(" ", corpo).strip()

    tags = (hashtags or "").replace(",", " ").strip()

    partes = []
    if titulo:
        partes.append(f"Título: {titulo.strip()}")
    if tags:
        partes.append(f"Palavras-chave: {tags}")
    if corpo:
        partes.append(corpo)

    texto = "\n".join(partes)
    return texto[:MAX_CHARS]


# ══════════════════════════════════════════════════════════════════════
# GERAÇÃO DO VETOR
# ══════════════════════════════════════════════════════════════════════
def gerar_embedding(texto: str, task_type: str = TASK_DOCUMENTO, api_key: str = None):
    """
    Converte texto em vetor de 768 dimensões via Gemini.

    Retorna list[float] (768 números) ou None em caso de falha.
    Passe api_key para reaproveitar a chave numa indexação em lote e evitar
    reler o BotConfig a cada artigo.
    """
    if not texto or not texto.strip():
        return None

    key = api_key or _get_api_key()
    if not key:
        logger.error("[EMBED] Sem chave Gemini configurada no BotConfig.")
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        resp = genai.embed_content(
            model=EMBED_MODEL,
            content=texto,
            task_type=task_type,
            output_dimensionality=EMBED_DIM,   # pede 768 em vez dos 3072 padrão
        )
        vetor = resp["embedding"]
        if not vetor or len(vetor) != EMBED_DIM:
            logger.error(f"[EMBED] Vetor com tamanho inesperado: {len(vetor) if vetor else 0}")
            return None
        # Ao reduzir a dimensão (3072→768), o gemini-embedding-001 NÃO devolve
        # o vetor normalizado. Normalizar (L2) é necessário pra similaridade
        # por cosseno/distância funcionar direito na busca. Sem numpy, na mão:
        norma = sum(x * x for x in vetor) ** 0.5
        if norma > 0:
            vetor = [x / norma for x in vetor]
        return vetor
    except Exception as e:
        logger.error(f"[EMBED] Falha ao gerar embedding: {e}")
        return None


def gerar_embedding_de_artigo(artigo, api_key: str = None):
    """Atalho: monta o texto do artigo e devolve o vetor (ou None)."""
    texto = limpar_para_embedding(artigo.titulo, artigo.hashtags, artigo.conteudo)
    return gerar_embedding(texto, task_type=TASK_DOCUMENTO, api_key=api_key)