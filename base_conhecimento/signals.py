# /base_conhecimento/signals.py
"""
Reindexação automática dos artigos da Base de Conhecimento.

POR QUE ISTO EXISTE
-------------------
O vetor semântico (campo `embedding`) é o que a IA usa pra ENCONTRAR o artigo.
Se alguém edita o texto de um artigo e o vetor não é regenerado, a busca
continua enxergando a versão ANTIGA — a IA acharia o artigo por um conteúdo
que não existe mais, ou não acharia por um que passou a existir.

Com este signal, todo save de Artigo dispara a regeneração do vetor.
Ninguém precisa lembrar de rodar `manage.py indexar_wiki` na mão.

COMO FUNCIONA
-------------
Roda numa thread separada porque a chamada ao Gemini leva ~1s. Assim quem
salvou o artigo vê a tela responder na hora, e o vetor é atualizado logo
atrás, em segundo plano.

Usa update() em vez de save() de propósito: não dispara outro post_save
(evita loop infinito) e não mexe no campo `atualizado_em` — indexar não é
editar o artigo.
"""
import logging
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Artigo
from .embeddings import gerar_embedding_de_artigo

logger = logging.getLogger("rastreador_zap")


@receiver(post_save, sender=Artigo)
def reindexar_artigo(sender, instance, **kwargs):
    """Regenera o vetor do artigo sempre que ele for salvo (criado ou editado)."""

    def _tarefa(pk):
        try:
            artigo = Artigo.objects.get(pk=pk)
            vetor = gerar_embedding_de_artigo(artigo)
            if vetor is not None:
                Artigo.objects.filter(pk=pk).update(
                    embedding=vetor,
                    embedding_atualizado_em=timezone.now(),
                )
                logger.info(f"[EMBED] Artigo {artigo.codigo} reindexado ao salvar.")
            else:
                logger.error(
                    f"[EMBED] Não consegui gerar o vetor do artigo {artigo.codigo}. "
                    f"Rode 'manage.py indexar_wiki' depois pra tentar de novo."
                )
        except Artigo.DoesNotExist:
            pass  # artigo apagado logo após salvar — nada a fazer
        except Exception as e:
            logger.error(f"[EMBED] Falha ao reindexar no save: {e}")

    threading.Thread(target=_tarefa, args=(instance.pk,), daemon=True).start()