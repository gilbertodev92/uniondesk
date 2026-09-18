from django.db import migrations, models


class Migration(migrations.Migration):
    """
    - Adiciona `tipo` (antes a classificação era adivinhada procurando a
      palavra "ERRO" no título, dentro do template).
    - `hashtags` passa a aceitar vazio.
    - Índices para a listagem por sistema e a busca por código.

    Não altera códigos já existentes: a nova geração só vale para artigos
    novos. Os antigos continuam válidos.
    """

    dependencies = [
        # ajuste se sua última migration tiver outro nome
        ("base_conhecimento", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="artigo",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("procedimento", "Procedimento"),
                    ("erro", "Erro / Troubleshooting"),
                    ("tutorial", "Tutorial"),
                    ("faq", "FAQ"),
                ],
                default="procedimento",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="artigo",
            name="hashtags",
            field=models.CharField(
                blank=True,
                help_text="Separe as hashtags por vírgula. Ex: instalação, erro, sql",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="artigo",
            name="codigo",
            field=models.CharField(db_index=True, editable=False, max_length=20, unique=True),
        ),
        migrations.AlterModelOptions(
            name="artigo",
            options={"ordering": ["-atualizado_em"]},
        ),
        migrations.AddIndex(
            model_name="artigo",
            index=models.Index(fields=["sistema", "-atualizado_em"], name="bc_artigo_sist_atual_idx"),
        ),
    ]