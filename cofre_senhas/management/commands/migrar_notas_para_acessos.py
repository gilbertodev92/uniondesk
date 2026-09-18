# cofre_senhas/management/commands/migrar_notas_para_acessos.py
"""
Converte credenciais que usam o campo NOTAS como lista de acessos
em registros estruturados de CredentialAccount.

Detecta o padrão em trincas de linhas:

    Nome do Cliente
    login@email.com
    senha

Uso:
    python manage.py migrar_notas_para_acessos              # simulação (não grava)
    python manage.py migrar_notas_para_acessos --credential 9
    python manage.py migrar_notas_para_acessos --apply      # grava
    python manage.py migrar_notas_para_acessos --apply --limpar-notas

Comece SEMPRE pelo dry-run e confira a saída. O parser é best-effort:
notas em formato livre podem não bater. O que não casar fica intacto.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from cofre_senhas.models import Credential, CredentialAccount

RE_EMAIL_OU_LOGIN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def parse_notas(texto: str):
    """
    Devolve (acessos, linhas_nao_reconhecidas).
    acessos = [{'label':..., 'username':..., 'password':...}, ...]
    """
    linhas = [l.strip() for l in (texto or "").splitlines()]
    linhas = [l for l in linhas if l]

    acessos, sobras = [], []
    i = 0
    while i < len(linhas):
        # procura a âncora: uma linha que é claramente um e-mail/login
        if i + 1 < len(linhas) and RE_EMAIL_OU_LOGIN.match(linhas[i + 1]):
            label = linhas[i]
            username = linhas[i + 1]
            password = linhas[i + 2] if i + 2 < len(linhas) else ""
            if password and not RE_EMAIL_OU_LOGIN.match(password):
                acessos.append({
                    "label": label,
                    "username": username,
                    "password": password,
                })
                i += 3
                continue
        sobras.append(linhas[i])
        i += 1

    return acessos, sobras


class Command(BaseCommand):
    help = "Converte notas em texto plano do cofre para acessos estruturados."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Grava de verdade. Sem isso, apenas simula.")
        parser.add_argument("--credential", type=int, default=None,
                            help="Processa apenas o ID informado.")
        parser.add_argument("--limpar-notas", action="store_true",
                            help="Após converter, limpa as notas originais.")

    def handle(self, *args, **opts):
        aplicar = opts["apply"]
        limpar = opts["limpar_notas"]

        qs = Credential.objects.all()
        if opts["credential"]:
            qs = qs.filter(pk=opts["credential"])

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "MODO SIMULAÇÃO — nada será gravado. Use --apply para valer.\n"
            ))

        total_cred = total_acc = 0

        for cred in qs:
            notas = cred.get_notes()
            if not notas:
                continue

            acessos, sobras = parse_notas(notas)
            if not acessos:
                continue

            total_cred += 1
            total_acc += len(acessos)

            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n[#{cred.pk}] {cred.title} — {len(acessos)} acesso(s) detectado(s)"
            ))
            for a in acessos:
                self.stdout.write(
                    f"   • {a['label']:<35} {a['username']:<38} senha: {'*' * len(a['password'])}"
                )
            if sobras:
                self.stdout.write(self.style.WARNING(
                    f"   ! {len(sobras)} linha(s) não reconhecida(s) — serão mantidas nas notas:"
                ))
                for s in sobras[:5]:
                    self.stdout.write(f"     - {s}")
                if len(sobras) > 5:
                    self.stdout.write(f"     ... e mais {len(sobras) - 5}")

            if not aplicar:
                continue

            with transaction.atomic():
                for ordem, a in enumerate(acessos):
                    acc = CredentialAccount(
                        credential=cred,
                        label=a["label"],
                        username=a["username"],
                        order=ordem,
                    )
                    acc.set_password(a["password"])
                    acc.save()

                if limpar:
                    # preserva o que o parser não entendeu
                    cred.set_notes("\n".join(sobras))
                    cred.save(update_fields=["encrypted_notes"])

        resumo = f"\n{total_cred} credencial(is), {total_acc} acesso(s)."
        if aplicar:
            self.stdout.write(self.style.SUCCESS("CONVERTIDO: " + resumo))
            if not limpar:
                self.stdout.write(self.style.WARNING(
                    "As notas originais foram MANTIDAS. Confira a tela e rode de novo "
                    "com --limpar-notas quando estiver seguro."
                ))
        else:
            self.stdout.write(self.style.WARNING("SIMULAÇÃO: " + resumo))
            self.stdout.write("Rode com --apply para gravar.")