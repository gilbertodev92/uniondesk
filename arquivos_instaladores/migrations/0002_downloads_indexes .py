from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("arquivos_instaladores", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="arquivoitem",
            name="downloads",
            field=models.PositiveIntegerField(default=0, editable=False, verbose_name="Downloads"),
        ),
        migrations.AlterField(
            model_name="arquivoitem",
            name="arquivo",
            field=models.FileField(blank=True, max_length=255, null=True,
                                   upload_to="arquivos_instaladores", verbose_name="Arquivo"),
        ),
        migrations.AddIndex(
            model_name="arquivoitem",
            index=models.Index(fields=["categoria", "-criado_em"], name="arq_cat_criado_idx"),
        ),
        migrations.AddIndex(
            model_name="arquivoitem",
            index=models.Index(fields=["is_ativo"], name="arq_ativo_idx"),
        ),
    ]