from django import forms
from .models import CalendarEvent, EventSource
from clientes_sistemas.models import Cliente

BR_DATETIME = "%d/%m/%Y %H:%M"

class EventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = [
            "title",
            "source",
            "cliente",       # <--- Novo campo principal
            "empresa_nome",  # Mantido como secundário
            "location",
            "description",
            "start",
            "end",
            "all_day",
            "is_background",
            "attendees",
        ]

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "ud-input",
                "placeholder": "Título do evento",
            }),
            "source": forms.Select(attrs={
                "class": "ud-input"
            }),
            "empresa_nome": forms.TextInput(attrs={
                "class": "ud-input",
                "placeholder": "Opcional: Nome livre caso não seja cliente cadastrado.",
            }),
            "location": forms.TextInput(attrs={
                "class": "ud-input",
                "placeholder": "Ex.: On-site, remoto, endereço do cliente…",
            }),
            "description": forms.Textarea(attrs={
                "class": "ud-input ud-input-textarea",
                "rows": 4,
            }),
            "start": forms.DateTimeInput(
                format=BR_DATETIME,
                attrs={
                    "class": "ud-input js-datetime",
                    "placeholder": "dd/mm/aaaa HH:MM",
                },
            ),
            "end": forms.DateTimeInput(
                format=BR_DATETIME,
                attrs={
                    "class": "ud-input js-datetime",
                    "placeholder": "dd/mm/aaaa HH:MM",
                },
            ),
            "all_day": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            "is_background": forms.CheckboxInput(attrs={
                "class": "ud-checkbox"
            }),
            "attendees": forms.SelectMultiple(attrs={
                "class": "ud-input js-attendees",
                "placeholder": "Selecione participantes…"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["start"].input_formats = [BR_DATETIME]
        self.fields["end"].input_formats = [BR_DATETIME]

        self.fields["source"].label = "Tipo do evento"
        self.fields["source"].initial = EventSource.MANUAL
        
        # Configuração do campo de Cliente para usar no TomSelect
        self.fields["cliente"].queryset = Cliente.objects.filter(ativo=True).order_by('razao_social')
        self.fields["cliente"].empty_label = "Selecione um cliente..."
        self.fields["cliente"].widget.attrs.update({"class": "ud-input", "id": "select-cliente"})