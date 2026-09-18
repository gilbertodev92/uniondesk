import re
from django import forms
from .models import Cliente

INPUT_CLASS = "w-full bg-core-deep border border-core-line text-ink rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-accent"
SELECT_CLASS = "w-full bg-core-deep border border-core-line text-ink rounded-lg px-3 py-2"

class ClienteForm(forms.ModelForm):

    class Meta:
        model = Cliente
        fields = "__all__"

        widgets = {
            # Dados principais
            "cnpj": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Apenas números"}),
            "razao_social": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "nome_fantasia": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "inscricao_estadual": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "telefone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "serial_sistema": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Ex: ABCD-1234-EFGH-5678"
            }),
            
            # Endereço
            "cep": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "logradouro": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "numero": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "bairro": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "cidade": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "estado": forms.TextInput(attrs={"class": INPUT_CLASS}),

            # Responsável
            "nome_responsavel": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "telefone_responsavel": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email_responsavel": forms.EmailInput(attrs={"class": INPUT_CLASS}),

            # ABC
            "faturamento_cliente": forms.Select(attrs={"class": SELECT_CLASS}),
            "visibilidade_cliente": forms.Select(attrs={"class": SELECT_CLASS}),

            # Sistemas (Trocado para Checkbox Múltiplo)
            "sistemas": forms.CheckboxSelectMultiple(attrs={
                # Adicionando um estilo visual bacana para os checkboxes combinarem com o tema escuro
                "class": "form-checkbox h-4 w-4 text-accent bg-core-panel border-core-line rounded focus:ring-accent cursor-pointer"
            }),

            # ==========================================
            # CAMPO NOVO: Observações
            # ==========================================
            "observacoes": forms.Textarea(attrs={
                "class": INPUT_CLASS,
                "rows": 4,
                "placeholder": "Digite aqui anotações importantes para o suporte. Elas aparecerão no chat da Ficha do Cliente..."
            }),
            
            # ==========================================
            # CAMPOS NOVOS: Regime e Data Consulta
            # ==========================================
            "regime_tributario": forms.TextInput(attrs={
                "class": INPUT_CLASS,
                "placeholder": "Puxado automaticamente..."
            }),
            "data_consulta_cnpj": forms.DateTimeInput(attrs={
                "class": INPUT_CLASS,
                "readonly": "readonly"
            }),
        }

    def clean_cnpj(self):
        # Valida duplicidade MANTENDO a máscara como padrão
        cnpj = self.cleaned_data.get('cnpj')
        numeros = re.sub(r'\D', '', str(cnpj))
        
        if len(numeros) == 14:
            cnpj_formatado = f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
        elif len(numeros) == 11:
            cnpj_formatado = f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
        else:
            cnpj_formatado = numeros
            
        if Cliente.objects.filter(cnpj=cnpj_formatado).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Este CNPJ/CPF já está cadastrado no sistema.")
            
        return cnpj_formatado