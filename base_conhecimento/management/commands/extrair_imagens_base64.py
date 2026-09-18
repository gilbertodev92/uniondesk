# /base_conhecimento/management/commands/extrair_imagens_base64.py
"""
Extrai as imagens embutidas em base64 (data:image/...;base64,...) do campo
`conteudo` dos artigos, grava cada uma como arquivo em MEDIA e reescreve o
`src` para apontar ao arquivo.

POR QUE
-------
Colar imagem no CKEditor gera base64 inline. Uma screenshot de 100 KB vira
~136 KB de texto dentro do registro. Isso:
  - incha o banco (backup, dump, replicação carregam tudo);
  - deixa a página pesada (nenhuma imagem é cacheada pelo navegador);
  - inviabiliza busca no conteúdo (icontains varre megabytes de ruído);
  - polui qualquer consumo automatizado do texto do artigo.

USO
---
    # 1. Simula. Não grava NADA. Comece sempre por aqui.
    python manage.py extrair_imagens_base64

    # 2. Um artigo só, para conferir o resultado na tela antes de ir em massa
    python manage.py extrair_imagens_base64 --artigo RA018 --apply

    # 3. Tudo, com backup (recomendado)
    python manage.py extrair_imagens_base64 --apply --backup ./backup_artigos

REVERTER
--------
    python manage.py extrair_imagens_base64 --restaurar ./backup_artigos

O backup guarda o `conteudo` original de cada artigo em JSON. Restaurar volta
exatamente o estado anterior (os arquivos em MEDIA continuam lá, inofensivos).
"""
import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from base_conhecimento.models import Artigo

# data:image/png;base64,iVBORw0...   (aspas simples ou duplas)
RE_DATA_IMG = re.compile(
    r"""data:image/(?P<ext>png|jpeg|jpg|gif|webp|bmp)\s*;\s*base64\s*,\s*(?P<dados>[A-Za-z0-9+/=\s]+)""",
    re.IGNORECASE,
)

EXT_NORMALIZADA = {"jpeg": "jpg"}


def _humanize(n: int) -> str:
    for unidade in ["B", "KB", "MB", "GB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} TB"


class Command(BaseCommand):
    help = "Extrai imagens base64 dos artigos para arquivos em MEDIA."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Grava de verdade. Sem isso, apenas simula.")
        parser.add_argument("--artigo", type=str, default=None,
                            help="Processa apenas o artigo com este código (ex.: RA018).")
        parser.add_argument("--backup", type=str, default=None,
                            help="Pasta para salvar o conteúdo original (permite reverter).")
        parser.add_argument("--restaurar", type=str, default=None,
                            help="Restaura o conteúdo a partir de uma pasta de backup.")
        parser.add_argument("--pasta", type=str, default="artigos",
                            help="Subpasta dentro de MEDIA_ROOT (padrão: artigos).")

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        if opts["restaurar"]:
            return self._restaurar(opts["restaurar"])

        aplicar = opts["apply"]
        pasta_backup = opts["backup"]

        if aplicar and not pasta_backup:
            self.stdout.write(self.style.WARNING(
                "Você está aplicando SEM --backup. Recomendo fortemente:\n"
                "  --backup ./backup_artigos\n"
            ))

        qs = Artigo.objects.all()
        if opts["artigo"]:
            qs = qs.filter(codigo__iexact=opts["artigo"])
            if not qs.exists():
                raise CommandError(f"Artigo '{opts['artigo']}' não encontrado.")

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "MODO SIMULAÇÃO — nada será gravado. Use --apply para valer.\n"
            ))

        if pasta_backup and aplicar:
            Path(pasta_backup).mkdir(parents=True, exist_ok=True)

        tot_artigos = tot_imgs = 0
        bytes_antes = bytes_depois = 0
        falhas = 0

        for artigo in qs.iterator():
            conteudo = artigo.conteudo or ""
            achados = list(RE_DATA_IMG.finditer(conteudo))
            if not achados:
                continue

            tamanho_antes = len(conteudo)
            novo_conteudo = conteudo
            extraidas = 0
            erros_artigo = []

            # substitui do fim para o começo para não bagunçar os offsets
            for m in reversed(achados):
                ext = m.group("ext").lower()
                ext = EXT_NORMALIZADA.get(ext, ext)
                dados_b64 = re.sub(r"\s+", "", m.group("dados"))

                try:
                    binario = base64.b64decode(dados_b64, validate=True)
                except (binascii.Error, ValueError) as e:
                    erros_artigo.append(f"base64 inválido ({e})")
                    falhas += 1
                    continue

                if len(binario) < 64:
                    erros_artigo.append("imagem muito pequena, ignorada")
                    continue

                # nome por hash: mesma imagem repetida = um arquivo só
                h = hashlib.sha256(binario).hexdigest()[:16]
                nome = f"{opts['pasta']}/{artigo.codigo}/{h}.{ext}"

                if aplicar:
                    if not default_storage.exists(nome):
                        nome = default_storage.save(nome, ContentFile(binario))
                    url = default_storage.url(nome)
                else:
                    url = f"[MEDIA]/{nome}"

                # troca só o trecho do data: pelo caminho do arquivo,
                # preservando o resto do atributo/tag intactos
                novo_conteudo = (
                    novo_conteudo[: m.start()] + url + novo_conteudo[m.end():]
                )
                extraidas += 1

            if extraidas == 0 and not erros_artigo:
                continue

            tot_artigos += 1
            tot_imgs += extraidas
            bytes_antes += tamanho_antes
            bytes_depois += len(novo_conteudo)

            economia = tamanho_antes - len(novo_conteudo)
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n[{artigo.codigo}] {artigo.titulo[:58]}"
            ))
            self.stdout.write(
                f"   {extraidas} imagem(ns) | {_humanize(tamanho_antes)} -> "
                f"{_humanize(len(novo_conteudo))} "
                f"(-{economia/tamanho_antes*100:.1f}%)"
            )
            for e in erros_artigo:
                self.stdout.write(self.style.WARNING(f"   ! {e}"))

            if not aplicar:
                continue

            if pasta_backup:
                destino = Path(pasta_backup) / f"{artigo.pk}.json"
                destino.write_text(json.dumps({
                    "pk": artigo.pk,
                    "codigo": artigo.codigo,
                    "titulo": artigo.titulo,
                    "conteudo": conteudo,
                }, ensure_ascii=False), encoding="utf-8")

            with transaction.atomic():
                # update() evita disparar o save() do model (que mexe em
                # codigo/slug) e não altera `atualizado_em` — isso aqui é
                # manutenção técnica, não edição do artigo.
                Artigo.objects.filter(pk=artigo.pk).update(conteudo=novo_conteudo)

        # ── resumo ──
        self.stdout.write("")
        if tot_artigos == 0:
            self.stdout.write(self.style.SUCCESS(
                "Nenhuma imagem base64 encontrada. Nada a fazer."
            ))
            return

        economia_total = bytes_antes - bytes_depois
        resumo = (
            f"{tot_artigos} artigo(s), {tot_imgs} imagem(ns).\n"
            f"  Campo `conteudo`: {_humanize(bytes_antes)} -> {_humanize(bytes_depois)}\n"
            f"  Economia no banco: {_humanize(economia_total)} "
            f"({economia_total/bytes_antes*100:.1f}%)"
        )
        if falhas:
            resumo += f"\n  {falhas} imagem(ns) com base64 inválido foram MANTIDAS como estavam."

        if aplicar:
            self.stdout.write(self.style.SUCCESS("CONCLUÍDO: " + resumo))
            if pasta_backup:
                self.stdout.write(
                    f"\nBackup em: {pasta_backup}\n"
                    f"Reverter:  python manage.py extrair_imagens_base64 --restaurar {pasta_backup}"
                )
            self.stdout.write(self.style.WARNING(
                "\nConfira alguns artigos na tela antes de apagar o backup."
            ))
        else:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO: " + resumo))
            self.stdout.write(
                "\nRode com --apply --backup ./backup_artigos para gravar."
            )

    # ------------------------------------------------------------------
    def _restaurar(self, pasta):
        p = Path(pasta)
        if not p.is_dir():
            raise CommandError(f"Pasta de backup não encontrada: {pasta}")

        arquivos = sorted(p.glob("*.json"))
        if not arquivos:
            raise CommandError(f"Nenhum backup .json em {pasta}")

        n = 0
        for f in arquivos:
            dados = json.loads(f.read_text(encoding="utf-8"))
            atualizados = Artigo.objects.filter(pk=dados["pk"]).update(
                conteudo=dados["conteudo"]
            )
            if atualizados:
                n += 1
                self.stdout.write(f"  restaurado [{dados['codigo']}] {dados['titulo'][:50]}")
            else:
                self.stdout.write(self.style.WARNING(
                    f"  artigo pk={dados['pk']} não existe mais, ignorado"
                ))

        self.stdout.write(self.style.SUCCESS(f"\n{n} artigo(s) restaurado(s)."))