from django import forms
from .models import EventoCS


class EventoCSForm(forms.ModelForm):

    class Meta:
        model = EventoCS
        fields = [
            "cliente",
            "responsavel",
            "tipo_contato",
            "motivo_risco", # <-- NOVO CAMPO DA NOSSA INTELIGÊNCIA
            "status",
            # "health_score", <-- O VILÃO FOI MORTO AQUI
            "gera_oportunidade",
            "data_prevista",
            "observacoes",
        ]

        widgets = {
            "cliente": forms.HiddenInput(),

            "responsavel": forms.Select(attrs={
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),

            "tipo_contato": forms.Select(attrs={
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),

            "motivo_risco": forms.Select(attrs={
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),

            "status": forms.Select(attrs={
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),

            "gera_oportunidade": forms.CheckboxInput(attrs={
                "class": "h-4 w-4 text-emerald-600"
            }),

            "data_prevista": forms.DateInput(attrs={
                "type": "date",
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),

            "observacoes": forms.Textarea(attrs={
                "rows": 4,
                "class": "w-full bg-slate-800 border border-slate-700 text-white rounded-lg px-3 py-2"
            }),
        }