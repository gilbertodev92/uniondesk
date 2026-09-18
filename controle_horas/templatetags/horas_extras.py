from decimal import Decimal, ROUND_HALF_UP
from django import template

register = template.Library()

def _to_hhmm(value, signed=False):
    if value is None:
        return "0:00"
    try:
        dec = Decimal(value)
    except Exception:
        return "0:00"

    sign = "-" if dec < 0 else ""
    dec = abs(dec)

    # arredonda para o minuto mais próximo
    total_minutes = int((dec * Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    h = total_minutes // 60
    m = total_minutes % 60
    text = f"{h}:{m:02d}"
    return f"{sign}{text}" if (signed and sign) else text

@register.filter
def hhmm(value):
    """Converte horas decimais para HH:MM (ex.: 4.75 -> 4:45)."""
    return _to_hhmm(value, signed=False)

@register.filter
def hhmm_signed(value):
    """Como hhmm, mas exibe o sinal quando negativo (ex.: -1.50 -> -1:30)."""
    return _to_hhmm(value, signed=True)

@register.filter
def weekday_pt(value):
    """Retorna o nome do dia da semana em português."""
    dias = {
        0: 'Segunda-feira',
        1: 'Terça-feira',
        2: 'Quarta-feira',
        3: 'Quinta-feira',
        4: 'Sexta-feira',
        5: 'Sábado',
        6: 'Domingo',
    }
    # Caso o valor passado seja um objeto date/datetime, usamos .weekday()
    # Caso seja o índice numérico, usamos o próprio valor
    try:
        index = value.weekday() if hasattr(value, 'weekday') else int(value)
        return dias.get(index, '')
    except Exception:
        return ''