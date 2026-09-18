from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Dependa da SUA 0003 existente:
        ('controle_horas', '0003_alter_apontamento_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='confighoras',
            name='pausa_almoco_min',
            field=models.PositiveIntegerField(
                default=60,
                help_text='Pausa padrão em minutos (ex.: 72 para 1h12).'
            ),
        ),
    ]
