from django.apps import AppConfig


class BaseConhecimentoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'base_conhecimento'

    def ready(self):
        # Registra os signals do app.
        # É o que liga a reindexação automática: sempre que um Artigo é salvo,
        # o vetor semântico usado pela busca da IA é regenerado em segundo plano.
        from . import signals  # noqa: F401