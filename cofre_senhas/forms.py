# cofre_senhas/forms.py
from django import forms
from django.forms import inlineformset_factory

from .models import Credential, CredentialAccount


class CredentialForm(forms.ModelForm):
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Preencha para definir ou alterar a senha.",
    )
    notes_plain = forms.CharField(
        label="Anotações",
        widget=forms.Textarea(attrs={"rows": 4}),
        required=False,
    )

    class Meta:
        model = Credential
        fields = ["title", "username", "tags", "is_favorite"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # BUG CORRIGIDO: ao editar, as notas não vinham preenchidas.
        # O usuário não conseguia ver nem apagar o que já estava salvo.
        if self.instance and self.instance.pk:
            self.fields["notes_plain"].initial = self.instance.get_notes()

    def save(self, commit=True, owner=None):
        inst = super().save(commit=False)
        if owner:
            inst.owner = owner

        pw = self.cleaned_data.get("password")
        if pw:
            inst.set_password(pw)

        # BUG CORRIGIDO: antes era `if notes:` — logo era IMPOSSÍVEL apagar
        # notas já salvas. Agora, se o campo veio no formulário, ele manda.
        if "notes_plain" in self.changed_data or not inst.pk:
            inst.set_notes(self.cleaned_data.get("notes_plain") or "")

        if commit:
            inst.save()
        return inst


class CredentialAccountForm(forms.ModelForm):
    """Um acesso individual (ex.: um cliente) dentro da credencial."""

    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(render_value=False, attrs={
            "placeholder": "Deixe em branco para manter",
            "autocomplete": "new-password",
        }),
        required=False,
    )

    class Meta:
        model = CredentialAccount
        fields = ["label", "username", "order"]
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "Ex.: Mercado Feller"}),
            "username": forms.TextInput(attrs={
                "placeholder": "login ou e-mail",
                "autocomplete": "off",
            }),
            "order": forms.HiddenInput(),
        }

    def clean(self):
        cleaned = super().clean()
        label = (cleaned.get("label") or "").strip()
        pw = cleaned.get("password")

        # linha nova precisa de senha; linha existente pode manter a atual
        if label and not pw and not self.instance.pk:
            self.add_error("password", "Informe a senha deste acesso.")
        return cleaned

    def save(self, commit=True):
        inst = super().save(commit=False)
        pw = self.cleaned_data.get("password")
        if pw:
            inst.set_password(pw)
        if commit:
            inst.save()
        return inst


CredentialAccountFormSet = inlineformset_factory(
    Credential,
    CredentialAccount,
    form=CredentialAccountForm,
    extra=0,
    can_delete=True,
)