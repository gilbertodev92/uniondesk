from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(field, css):
    """{{ form.campo|add_class:"minha-classe" }}"""
    return field.as_widget(attrs={"class": css})