from django.db import migrations
import ckeditor_uploader.fields

class Migration(migrations.Migration):

    dependencies = [
        ("base_conhecimento", "0002_alter_artigo_conteudo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="artigo",
            name="conteudo",
            field=ckeditor_uploader.fields.RichTextUploadingField(),
        ),
    ]
