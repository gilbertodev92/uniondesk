# /base_conhecimento/toc.py
"""
Gera o índice (sumário) de um artigo a partir do HTML já sanitizado.

O PROBLEMA
----------
Os artigos não usam <h2>/<h3>. Quem escreve no CKEditor formata o título do
passo com fonte maior e negrito, gerando algo assim:

    <p><strong><span style="font-size:18px">Passo 3 - Como configurar...</span></strong></p>
    <p><span style="font-size:12pt">Passo 1 - Atualize o sistema...</span></p>

Um índice que procurasse só por <h2> viria vazio em 100% do conteúdo atual.

A SOLUÇÃO
---------
Reconhece as duas formas:
  1. headings de verdade (<h1>..<h4>) — o jeito certo, para o conteúdo novo;
  2. pseudo-títulos: <p> cujo texto casa com um padrão ("Passo 3 - ...") ou
     que está em negrito com fonte grande.

Assim o índice funciona no conteúdo que já existe, sem precisar reescrever
69 artigos. Conforme a equipe passar a usar H2 no editor, o item 1 assume
naturalmente.
"""
import re
import unicodedata

from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

# "Passo 1 -", "Etapa 2:", "1. Configurar", "PASSO 10"
RE_PSEUDO_TITULO = re.compile(
    r"^\s*(passo|etapa|parte|fase|step)\s*\d+\s*[-–—:.)]|^\s*\d{1,2}\s*[-–—.)]\s+\S",
    re.IGNORECASE,
)

RE_HEADING = re.compile(r"<(h[1-4])\b([^>]*)>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL)
RE_PARAGRAFO = re.compile(r"<p\b([^>]*)>(.*?)</p\s*>", re.IGNORECASE | re.DOTALL)

# font-size: 18px / 14pt / 1.2em
RE_FONT_SIZE = re.compile(r"font-size\s*:\s*([\d.]+)\s*(px|pt|em|rem)", re.IGNORECASE)

# corpo de texto costuma ser 12pt/16px; acima disso é título
LIMIAR_PX = 16.0
LIMIAR_PT = 13.0


def _slugify(texto: str, usados: set) -> str:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    base = re.sub(r"[^\w\s-]", "", base).strip().lower()
    base = re.sub(r"[-\s]+", "-", base)[:50] or "secao"
    slug, n = base, 2
    while slug in usados:
        slug = f"{base}-{n}"
        n += 1
    usados.add(slug)
    return slug


def _fonte_grande(html_trecho: str) -> bool:
    for valor, unidade in RE_FONT_SIZE.findall(html_trecho):
        try:
            v = float(valor)
        except ValueError:
            continue
        u = unidade.lower()
        if u == "px" and v >= LIMIAR_PX:
            return True
        if u == "pt" and v >= LIMIAR_PT:
            return True
        if u in ("em", "rem") and v >= 1.15:
            return True
    return False


def _limpar(texto: str) -> str:
    t = strip_tags(texto)
    t = t.replace("&nbsp;", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def construir_toc(html: str):
    """
    Recebe HTML sanitizado. Devolve (html_com_ancoras, itens).

    itens = [{"id": "passo-1", "texto": "Passo 1 - ...", "nivel": 2}, ...]
    """
    if not html:
        return mark_safe(""), []

    candidatos = []  # (inicio, fim, tag, attrs, interno, nivel)

    # 1) headings de verdade
    for m in RE_HEADING.finditer(html):
        tag, attrs, interno = m.group(1), m.group(2), m.group(3)
        texto = _limpar(interno)
        if not texto:
            continue
        nivel = min(int(tag[1]), 3)
        candidatos.append((m.start(), m.end(), tag, attrs, interno, nivel, texto))

    # 2) pseudo-títulos (só se não houver heading de verdade suficiente)
    if len(candidatos) < 2:
        for m in RE_PARAGRAFO.finditer(html):
            attrs, interno = m.group(1), m.group(2)
            texto = _limpar(interno)
            if not texto or len(texto) > 120:
                continue

            é_passo = bool(RE_PSEUDO_TITULO.match(texto))
            é_destaque = ("<strong" in interno.lower() or "<b>" in interno.lower()) \
                and _fonte_grande(interno) and len(texto) <= 90

            if é_passo or é_destaque:
                nivel = 2 if é_passo else 3
                candidatos.append((m.start(), m.end(), "p", attrs, interno, nivel, texto))

    if not candidatos:
        return mark_safe(html), []

    candidatos.sort(key=lambda c: c[0])

    usados, itens = set(), []
    for c in candidatos:
        itens.append({"id": _slugify(c[6], usados), "texto": c[6], "nivel": c[5]})

    # índice de 1 item não ajuda ninguém
    if len(itens) < 2:
        return mark_safe(html), []

    # injeta os ids, do fim para o começo (não bagunça os offsets)
    novo = html
    for c, item in reversed(list(zip(candidatos, itens))):
        inicio, fim, tag, attrs, interno, _, _ = c
        if re.search(r'\bid\s*=', attrs, re.IGNORECASE):
            attrs_novos = re.sub(r'\bid\s*=\s*["\'][^"\']*["\']',
                                 f'id="{item["id"]}"', attrs, count=1, flags=re.IGNORECASE)
        else:
            attrs_novos = f'{attrs} id="{item["id"]}"'
        substituto = f"<{tag}{attrs_novos} class=\"kb-anchor\">{interno}</{tag}>"
        novo = novo[:inicio] + substituto + novo[fim:]

    return mark_safe(novo), itens