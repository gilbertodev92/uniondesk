"""
Reimporta as carteiras do backup, CONVERTENDO saldo+XP em Pó Mágico.
Rode DEPOIS de recriar o schema (migrate) e popular os itens.

Fórmula: po = min( sqrt(moedas + xp) * 1.5 , 250 )
Todos voltam ao Nível 1, saldo e XP zerados, com o pó de largada.

Uso:  python manage.py importar_carteiras
"""
import json
import math
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from recompensas.models import Carteira

User = get_user_model()
TETO_PO = 250
FATOR = 1.5


class Command(BaseCommand):
    help = "Reimporta carteiras convertendo saldo em pó mágico."

    def handle(self, *args, **opts):
        try:
            with open("carteiras_backup.json", encoding="utf-8") as f:
                dados = json.load(f)
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR("carteiras_backup.json não encontrado. Rode exportar_carteiras antes."))
            return

        convertidas = 0
        for d in dados:
            try:
                user = User.objects.get(id=d["usuario_id"])
            except User.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"• usuário {d['username']} não existe mais (pulado)"))
                continue

            total = d["saldo_moedas"] + d["xp_total"]
            po = int(min(math.sqrt(total) * FATOR, TETO_PO)) if total > 0 else 0

            carteira, _ = Carteira.objects.get_or_create(usuario=user)
            carteira.po_magico = po
            carteira.saldo_moedas = 0
            carteira.xp_total = 0
            carteira.nivel_atual = 1
            carteira.ofensiva_diaria = 0
            carteira.save()
            convertidas += 1
            self.stdout.write(f"  {d['username']:15} saldo {total:>7} → {po} pó")

        self.stdout.write(self.style.SUCCESS(f"\n✓ {convertidas} carteiras convertidas. Corrida nova começou!"))
