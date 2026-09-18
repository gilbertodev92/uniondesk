from django import forms
from .models import ArquivoItem


class ArquivoItemForm(forms.ModelForm):
    class Meta:
        model = ArquivoItem
        # `arquivo` NÃO entra no form: o upload é feito em chunks via JS,
        # não pelo campo <input type=file> do form padrão.
        fields = ["titulo", "categoria", "versao", "descricao", "link_externo", "is_ativo"]
        widgets = {
            "descricao": forms.Textarea(attrs={"rows": 3}),
        }