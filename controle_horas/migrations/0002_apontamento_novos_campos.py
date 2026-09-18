from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('controle_horas', '0001_initial'),
    ]

    operations = [
        # --- Novos campos de marcação (4 pontos e 2 pontos)
        migrations.AddField(
            model_name='apontamento',
            name='manha_inicio',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='manha_fim',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='tarde_inicio',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='tarde_fim',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='especial_inicio',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='especial_fim',
            field=models.TimeField(null=True, blank=True),
        ),

        # --- Totais em HORAS (deixa default 0.00 para popular registros existentes)
        migrations.AddField(
            model_name='apontamento',
            name='horas_total',
            field=models.DecimalField(default=Decimal('0.00'), max_digits=6, decimal_places=2, editable=False),
        ),
        migrations.AddField(
            model_name='apontamento',
            name='horas_extra',
            field=models.DecimalField(default=Decimal('0.00'), max_digits=6, decimal_places=2, editable=False),
        ),

        # --- Tipo (se ainda não existir). Se já existir, pode remover este bloco.
        # migrations.AddField(
        #     model_name='apontamento',
        #     name='tipo',
        #     field=models.CharField(max_length=20, choices=[
        #         ('normal', 'Normal (4 marcações)'),
        #         ('plantao', 'Plantão (2 marcações)'),
        #         ('atualizacao', 'Atualização (2 marcações)'),
        #         ('emergencia', 'Atendimento Emergência (2 marcações)'),
        #         ('implantacao', 'Implantação (2 marcações)'),
        #     ], default='normal'),
        # ),

        # --- NÃO vamos remover colunas antigas aqui (ex.: hora_inicio, minutos_total)
        # para evitar quebra se existirem dependências. Depois limpamos em outra migração.
    ]
