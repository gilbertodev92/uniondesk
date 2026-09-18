# /base_conhecimento/management/commands/comparar_busca.py
"""
Compara, LADO A LADO, a busca ANTIGA (palavra-chave) com a NOVA (semântica)
para uma mesma pergunta. Serve pra você validar a qualidade antes de plugar
a busca nova no bot.

USO:
    python manage.py comparar_busca "nota fiscal não sai"
    python manage.py comparar_busca "impressora não imprime cupom" --cliente 42

O --cliente <codigo> faz a busca nova filtrar pelos sistemas daquele cliente
(o codigo é o campo `codigo` do Cliente, que é a PK/AutoField).
"""
from django.core.management.base import BaseCommand

from base_conhecimento.models import Artigo
from base_conhecimento.busca import buscar
from base_conhecimento.views import filtro_busca  # a busca antiga, reaproveitada


class Command(BaseCommand):
    help = "Compara a busca antiga (keyword) com a nova (semântica) lado a lado."

    def add_arguments(self, parser):
        parser.add_argument("pergunta", type=str, help="A frase a buscar (entre aspas).")
        parser.add_argument("--cliente", type=int, default=None,
                            help="Código do cliente, pra filtrar por sistema na busca nova.")

    def handle(self, *args, **opts):
        pergunta = opts["pergunta"]
        cliente = None
        nome_cliente = "— (sem filtro de sistema)"

        if opts["cliente"]:
            try:
                from clientes_sistemas.models import Cliente
                cliente = Cliente.objects.get(pk=opts["cliente"])
                sis = ", ".join(s.nome for s in cliente.sistemas.all()) or "nenhum sistema vinculado"
                nome_cliente = f"{cliente.razao_social}  [sistemas: {sis}]"
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Cliente não encontrado: {e}"))
                return

        larg = 78
        self.stdout.write("═" * larg)
        self.stdout.write(f"PERGUNTA : {pergunta}")
        self.stdout.write(f"CLIENTE  : {nome_cliente}")
        self.stdout.write("═" * larg)

        # ── BUSCA ANTIGA (icontains em titulo/codigo/hashtags) ────────
        self.stdout.write(self.style.WARNING("\n▼ BUSCA ANTIGA (palavra-chave)\n"))
        antigos = (
            Artigo.objects.filter(filtro_busca(pergunta))
            .select_related("sistema")
            .order_by("-atualizado_em")[:5]
        )
        if not antigos:
            self.stdout.write("   (nada encontrado)")
        for a in antigos:
            self.stdout.write(f"   • [{a.codigo}] {a.titulo}  — {a.sistema}")

        # ── BUSCA NOVA (semântica + filtro de sistema) ────────────────
        self.stdout.write(self.style.SUCCESS("\n▼ BUSCA NOVA (significado)\n"))
        res = buscar(pergunta, cliente=cliente)

        if res.get("erro"):
            self.stdout.write(self.style.ERROR(f"   ERRO: {res['erro']}"))
            return

        if res.get("fora_do_sistema"):
            self.stdout.write(self.style.WARNING(
                "   ⚠️  (sem acerto no sistema do cliente — resultados de OUTROS sistemas)\n"
            ))

        if not res["resultados"]:
            self.stdout.write("   (nada encontrado)")
        for r in res["resultados"]:
            a = r["artigo"]
            # distância menor = mais parecido; mostro como % de proximidade
            prox = max(0, (1 - r["distancia"])) * 100
            flag = " 🌐fora-do-sistema" if r.get("fora_do_sistema") else ""
            self.stdout.write(
                f"   • [{a.codigo}] {a.titulo}  — {a.sistema}"
                f"   ({prox:.0f}% · via {r['via']}{flag})"
            )

        self.stdout.write("\n" + "═" * larg)
        self.stdout.write("Compare: a nova achou coisas que a antiga não achou? Alguma veio errada?")
        self.stdout.write("═" * larg + "\n")