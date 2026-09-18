# /base_conhecimento/management/commands/indexar_wiki.py
"""
Gera (ou regenera) os vetores semânticos dos artigos da Base de Conhecimento.

USO:
    python manage.py indexar_wiki                # indexa só os que faltam
    python manage.py indexar_wiki --force        # reindexa TODOS
    python manage.py indexar_wiki --id CLI15-003 # um artigo específico (por código)

É seguro rodar quantas vezes quiser. Por padrão só processa artigos sem vetor
(ou editados depois da última indexação), então re-executar é barato.
"""
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from base_conhecimento.models import Artigo
from base_conhecimento.embeddings import gerar_embedding_de_artigo, _get_api_key


class Command(BaseCommand):
    help = "Gera os embeddings (vetores de busca) dos artigos da base de conhecimento."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Reindexa todos os artigos, mesmo os que já têm vetor.",
        )
        parser.add_argument(
            "--id", type=str, default=None,
            help="Indexa apenas o artigo com este código (ex: CLI15-003).",
        )
        parser.add_argument(
            "--pausa", type=float, default=0.5,
            help="Segundos de pausa entre chamadas à API (padrão 0.5).",
        )

    def handle(self, *args, **opts):
        # 1) A chave existe? Falha cedo com mensagem clara.
        if not _get_api_key():
            self.stderr.write(self.style.ERROR(
                "❌ Sem chave Gemini no BotConfig. Configure em /admin/ (Configuração do Bot) "
                "antes de indexar."
            ))
            return

        # 2) Monta o conjunto de artigos a processar
        qs = Artigo.objects.all().order_by("codigo")

        if opts["id"]:
            qs = qs.filter(codigo=opts["id"])
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"❌ Nenhum artigo com código {opts['id']}."))
                return
        elif not opts["force"]:
            # só os que não têm vetor OU foram editados depois de indexados
            from django.db.models import Q, F
            qs = qs.filter(
                Q(embedding__isnull=True)
                | Q(embedding_atualizado_em__isnull=True)
                | Q(atualizado_em__gt=F("embedding_atualizado_em"))
            )

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "✅ Nada a indexar — todos os artigos já estão atualizados. "
                "(Use --force para reindexar tudo.)"
            ))
            return

        modo = "REINDEXANDO TODOS" if opts["force"] else "indexando pendentes"
        self.stdout.write(f"🧠 {modo}: {total} artigo(s).\n")

        # 3) Reusa a chave em todas as chamadas (não relê o banco a cada artigo)
        api_key = _get_api_key()
        ok, falhas = 0, 0

        for i, artigo in enumerate(qs.iterator(), start=1):
            rotulo = f"[{i}/{total}] {artigo.codigo} — {artigo.titulo[:45]}"
            vetor = gerar_embedding_de_artigo(artigo, api_key=api_key)

            if vetor is None:
                falhas += 1
                self.stdout.write(self.style.WARNING(f"  ⚠️  {rotulo}  → FALHOU (pulado)"))
            else:
                # update() direto: não dispara o save() do model nem mexe em
                # atualizado_em (indexar não é editar o artigo)
                Artigo.objects.filter(pk=artigo.pk).update(
                    embedding=vetor,
                    embedding_atualizado_em=timezone.now(),
                )
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"  ✅ {rotulo}"))

            # respeita o rate limit da API de embeddings
            if i < total:
                time.sleep(opts["pausa"])

        # 4) Resumo final
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"🏁 Concluído: {ok} indexado(s), {falhas} falha(s)."))
        if falhas:
            self.stdout.write(
                "   Rode de novo pra tentar os que falharam (só eles serão reprocessados)."
            )