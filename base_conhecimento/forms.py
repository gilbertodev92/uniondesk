# /base_conhecimento/forms.py
from django import forms
from .models import Artigo
from ckeditor_uploader.fields import RichTextUploadingFormField


class ArtigoForm(forms.ModelForm):
    # NOTA: era `CKEditorWidget` (sem upload) num campo que no model é
    # RichTextUploadingField. Isso tirava o botão de enviar imagem justamente
    # onde ele mais importa — documentação técnica é feita de screenshots.
    conteudo = RichTextUploadingFormField(label="Conteúdo")

    class Meta:
        model = Artigo
        fields = ["titulo", "tipo", "hashtags", "conteudo"]
        widgets = {
            "titulo": forms.TextInput(attrs={
                "placeholder": "Ex.: Erro 404 ao emitir NF-e",
                "autofocus": "autofocus",
            }),
            "tipo": forms.Select(),
            "hashtags": forms.TextInput(attrs={
                "placeholder": "instalação, erro, sql",
            }),
        }
        help_texts = {
            "hashtags": "Separe por vírgula. Não precisa do #.",
            "tipo": "Define a tarja de cor e ajuda a filtrar a lista.",
        }

    def clean_hashtags(self):
        # normaliza: remove #, espaços sobrando e duplicatas, mantém a ordem
        bruto = self.cleaned_data.get("hashtags") or ""
        vistos, saida = set(), []
        for t in bruto.split(","):
            t = t.strip().lstrip("#")
            if t and t.lower() not in vistos:
                vistos.add(t.lower())
                saida.append(t)
        return ", ".join(saida)