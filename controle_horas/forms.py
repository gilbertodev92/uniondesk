# /home/logica/projetos/union/controle_horas/forms.py
from django import forms
from .models import Apontamento

class ApontamentoForm(forms.ModelForm):
    class Meta:
        model = Apontamento
        fields = [
            'data', 'tipo', 'sistema', 'descricao',
            'manha_inicio','manha_fim','tarde_inicio','tarde_fim',
            'especial_inicio','especial_fim',
        ] if hasattr(Apontamento, 'sistema') else [
            'data','tipo','descricao',
            'manha_inicio','manha_fim','tarde_inicio','tarde_fim',
            'especial_inicio','especial_fim',
        ]
        widgets = {
            'data': forms.DateInput(attrs={'type':'date', 'class':'ud-input'}),
            'tipo': forms.Select(attrs={'class':'ud-input'}),
            'descricao': forms.Textarea(attrs={'rows':3, 'class':'ud-input'}),
            'manha_inicio': forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
            'manha_fim':    forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
            'tarde_inicio': forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
            'tarde_fim':    forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
            'especial_inicio': forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
            'especial_fim':    forms.TimeInput(attrs={'type':'time', 'class':'ud-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        # delega pro model.clean(); aqui só possível UX extra se quiser
        return cleaned
