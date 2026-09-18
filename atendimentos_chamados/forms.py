from django import forms
from .models import Atendimento


class AtendimentoForm(forms.ModelForm):

    class Meta:
        model = Atendimento
        fields = [
            "cliente",
            "numero_os",
            "titulo",
            "descricao",
            "prioridade",
            "setor_atual",
            "implantacao_cliente_novo",
            "implantacao_modulo_novo",
            "possui_treinamento",
            "tipo_treinamento",
            "abrir_cs_pos_atendimento",
            "whatsapp_contato", "flag_conversao_dados", "flag_instalacao_equip", 
            "flag_tef_incluso", "flag_mobilidade", "flag_backup",
            "trein_cadastros", "trein_entrada_nf", "trein_saida_nf", "trein_nfce", 
            "trein_estoque", "trein_financeiro", "trein_boletos", "flag_data_center", "trein_os_service"
        ]

        widgets = {
            "cliente": forms.HiddenInput(),

            "numero_os": forms.TextInput(attrs={
                "class": "ud-input"
            }),
            "titulo": forms.TextInput(attrs={
                "class": "ud-input"
            }),
            "descricao": forms.Textarea(attrs={
                "class": "ud-textarea",
                "rows": 4
            }),
            "prioridade": forms.Select(attrs={
                "class": "ud-select"
            }),
            "setor_atual": forms.Select(attrs={
                "class": "ud-select"
            }),
            "tipo_treinamento": forms.Select(attrs={
                "class": "ud-select"
            }),
            "implantacao_cliente_novo": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            "implantacao_modulo_novo": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            "possui_treinamento": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            "abrir_cs_pos_atendimento": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            # Checkboxes de Implantação
            "flag_conversao_dados": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "flag_instalacao_equip": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "flag_tef_incluso": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "flag_mobilidade": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "flag_backup": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "flag_data_center": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            
            # Checkboxes de Treinamento
            "trein_cadastros": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_entrada_nf": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_saida_nf": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_nfce": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_estoque": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_financeiro": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_boletos": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
            "trein_os_service": forms.CheckboxInput(attrs={"class": "ud-checkbox"}),
        }