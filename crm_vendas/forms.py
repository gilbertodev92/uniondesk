from django import forms
from django.contrib.auth import get_user_model
from .models import Lead

User = get_user_model()

INPUT_CLASS = "modal-input"
SELECT_CLASS = "modal-select"

class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'cnpj', 'nome_empresa', 'nome_contato', 'telefone', 'cidade', 'segmento', 'origem',
            'etapa', 'vendedor_responsavel', 'urgencia',
            'valor_equipamentos', 'valor_mensalidade', 'valor_servicos',
            'forma_pagamento', 'prazo_pagamento',
            'dor_principal'
        ]
        widgets = {
            'cnpj': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Apenas números', 'id': 'id_lead_cnpj'}),
            'nome_empresa': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Padaria do João', 'id': 'id_lead_nome_empresa'}),
            'nome_contato': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Com quem falamos?'}),
            'telefone': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': '(00) 00000-0000', 'id': 'id_lead_telefone'}),
            'cidade': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Cidade - UF', 'id': 'id_lead_cidade'}),
            'segmento': forms.Select(attrs={'class': SELECT_CLASS}),
            
            'origem': forms.Select(attrs={'class': SELECT_CLASS}),
            'etapa': forms.Select(attrs={'class': SELECT_CLASS}),
            'vendedor_responsavel': forms.Select(attrs={'class': SELECT_CLASS}),
            'urgencia': forms.Select(attrs={'class': SELECT_CLASS}),
            
            'valor_equipamentos': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'}),
            'valor_mensalidade': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'}),
            'valor_servicos': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'}),
            
            'forma_pagamento': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Boleto, Pix, Cartão'}),
            'prazo_pagamento': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: À vista, 30/60/90'}),
            
            'dor_principal': forms.Textarea(attrs={'class': INPUT_CLASS, 'rows': 2, 'placeholder': 'Qual a necessidade do cliente?'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ==========================================
        # FILTRO DE USUÁRIOS: APENAS GRUPO COMERCIAL
        # ==========================================
        # Busca usuários que pertencem a qualquer grupo que contenha "Comercial" no nome
        vendedores = User.objects.filter(groups__name__icontains='Comercial').distinct()
        
        if vendedores.exists():
            self.fields['vendedor_responsavel'].queryset = vendedores
        else:
            # Fallback caso o grupo não tenha sido criado ainda no painel Admin
            self.fields['vendedor_responsavel'].queryset = User.objects.filter(is_active=True)