from django import forms
from .models import Sistema

class SistemaForm(forms.ModelForm):
    class Meta:
        model = Sistema
        fields = ["nome", "fabricante"]

        widgets = {
            "nome": forms.TextInput(attrs={
                "class": "w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500",
                "placeholder": "Digite o nome do sistema"
            }),
            "fabricante": forms.TextInput(attrs={
                "class": "w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500",
                "placeholder": "Digite o fabricante"
            }),
        }
