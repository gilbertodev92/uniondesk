# /base_conhecimento/sanitize.py
"""
Sanitização do HTML vindo do CKEditor.

O conteúdo era renderizado com `{{ artigo.conteudo|safe }}` — HTML cru do editor
direto na página (XSS armazenado). `|safe` só é aceitável em HTML sanitizado.

DEPENDÊNCIA: pip install nh3
Sem nh3/bleach o texto é ESCAPADO — seguro, mas aparece como código na tela.
Este módulo NUNCA levanta exceção: na falha, escapa. Sanitização que derruba a
página é pior que o problema que resolve.
"""
import logging

from django.utils.html import escape
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

# Detecta o backend UMA vez, no import. Erro de import/versão vira
# "escapa tudo", nunca um 500 por requisição.
_BACKEND = None
try:
    import nh3  # type: ignore
    _BACKEND = "nh3"
except Exception:
    try:
        import bleach  # type: ignore
        from bleach.css_sanitizer import CSSSanitizer  # noqa: F401
        _BACKEND = "bleach"
    except Exception:
        logger.error(
            "base_conhecimento: nem nh3 nem bleach disponiveis. O conteudo dos "
            "artigos sera ESCAPADO (aparece como codigo). Rode: pip install nh3"
        )

TAGS_PERMITIDAS = {
    "p", "br", "hr", "div", "span",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sub", "sup", "mark", "small",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "code", "kbd", "samp",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "a", "img", "figure", "figcaption",
}

ATRIBUTOS_PERMITIDOS = {
    "*": {"class", "style", "title", "id"},
    # NOTA: "rel" NÃO entra aqui. O nh3 gerencia o rel sozinho (adiciona
    # noopener/noreferrer) e levanta ValueError se a gente declarar. Era
    # exatamente esse erro que virava 500 na página do artigo.
    "a": {"href", "target"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align", "scope"},
    "col": {"span", "width"},
    "table": {"border", "cellpadding", "cellspacing", "width"},
}

CSS_PERMITIDO = {
    "color", "background-color", "text-align", "font-weight", "font-style",
    "text-decoration", "width", "height", "margin", "padding", "border",
    "border-collapse", "vertical-align", "font-size", "line-height",
}

# ── Sobre o "data:" ─────────────────────────────────────────────────
# Os artigos têm screenshots embutidas como data:image/png;base64,...
# (o CKEditor cola imagem assim). Se "data" não estiver aqui, o
# sanitizador APAGA o src e todas as imagens somem.
#
# Mas data: é perigoso fora de <img>: `data:text/html;base64,...` num
# <a href> executa HTML arbitrário ao clicar. Por isso liberamos o
# esquema e restringimos no `_filtro_atributo` abaixo: data: só vale em
# img/src e só se for data:image/.
PROTOCOLOS_PERMITIDOS = {"http", "https", "mailto", "data"}


def _filtro_atributo(tag: str, attr: str, valor: str):
    """Devolve o valor aceito, ou None para remover o atributo."""
    v = (valor or "").strip().lower()
    if v.startswith("data:"):
        if tag == "img" and attr == "src" and v.startswith("data:image/"):
            return valor          # screenshot legítima do editor
        return None               # data: em qualquer outro lugar: fora
    return valor


def _clean_nh3(html: str) -> str:
    import nh3
    return nh3.clean(
        html,
        tags=TAGS_PERMITIDAS,
        attributes={k: set(v) for k, v in ATRIBUTOS_PERMITIDOS.items()},
        url_schemes=PROTOCOLOS_PERMITIDOS,
        attribute_filter=_filtro_atributo,
    )


def _clean_bleach(html: str) -> str:
    import bleach
    from bleach.css_sanitizer import CSSSanitizer
    css = CSSSanitizer(allowed_css_properties=sorted(CSS_PERMITIDO))
    return bleach.clean(
        html,
        tags=sorted(TAGS_PERMITIDAS),
        attributes={k: sorted(v) for k, v in ATRIBUTOS_PERMITIDOS.items()},
        protocols=sorted(PROTOCOLOS_PERMITIDOS),
        css_sanitizer=css,
        strip=True,
    )


def limpar_html(html: str) -> str:
    """Devolve HTML seguro. NUNCA levanta — na falha, escapa."""
    if not html:
        return ""
    try:
        if _BACKEND == "nh3":
            return _clean_nh3(html)
        if _BACKEND == "bleach":
            return _clean_bleach(html)
    except Exception:
        logger.exception("base_conhecimento: falha ao sanitizar; escapando.")
    return escape(html)


def conteudo_seguro(html: str):
    """Pronto para o template (ja marcado safe)."""
    return mark_safe(limpar_html(html))