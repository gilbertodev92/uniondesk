# calendairo_agenda/templatetags/form_extras.py
from django import template
from django.utils.safestring import mark_safe
from django.utils.html import conditional_escape

register = template.Library()

def _merge_attrs(bound_field, extra):
    """Devolve HTML do campo com attrs mesclados."""
    attrs = {}
    # copia attrs atuais do widget (se existirem)
    if hasattr(bound_field.field, "widget"):
        attrs.update(getattr(bound_field.field.widget, "attrs", {}) or {})
    # mescla novos
    attrs.update(extra or {})
    return bound_field.as_widget(attrs=attrs)

@register.filter
def add_class(field, css_classes):
    """
    Adiciona classes CSS ao widget. Se field já for SafeString (HTML renderizado),
    apenas retorna como está (evita quebrar encadeamentos).
    """
    # se já é HTML pronto, não temos como reabrir o widget -> retorna como veio
    if not hasattr(field, "as_widget"):
        return field
    current = (getattr(field.field.widget, "attrs", {}) or {}).get("class", "")
    new = (current + " " + (css_classes or "")).strip()
    return mark_safe(_merge_attrs(field, {"class": new}))

@register.filter
def add_attr(field, arg):
    """
    Define um atributo simples no widget. Uso: |add_attr:"placeholder:Meu texto"
    Se field já for SafeString, retorna como veio (não quebra).
    """
    if not hasattr(field, "as_widget"):
        return field
    try:
        name, val = [s.strip() for s in str(arg).split(":", 1)]
    except ValueError:
        return field
    # trata classe de forma aditiva
    if name == "class":
        current = (getattr(field.field.widget, "attrs", {}) or {}).get("class", "")
        val = (current + " " + val).strip()
    return mark_safe(_merge_attrs(field, {name: conditional_escape(val)}))
