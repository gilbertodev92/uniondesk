# /home/logica/projetos/union/arquivos_instaladores/templatetags/add_class.py
from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    """
    Uso no template:
    {{ form.campo|add_class:"minha-classe" }}
    """
    return field.as_widget(attrs={"class": css})
