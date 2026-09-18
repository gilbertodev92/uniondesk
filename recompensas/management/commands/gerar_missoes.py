"""
Gera as missões ativas sorteando moldes. Idempotente: se já existem missões
do tipo para o período, não duplica.

Uso:
    python manage.py gerar_missoes            # gera o que estiver faltando (diária/semanal/mensal conforme a data)
    python manage.py gerar_missoes --tipo DIARIA
    python manage.py gerar_missoes --forcar   # recria mesmo se já existir

Ideal no cron:
    00:05 todo dia   → gerar_missoes --tipo DIARIA
    segunda 00:10    → gerar_missoes --tipo SEMANAL
    dia 1 00:15      → gerar_missoes --tipo MENSAL
(ou só 'gerar_missoes' diário, que ele descobre o que falta)
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from recompensas.models import MoldeMissao, MissaoAtiva

# quantas missões de cada tipo ficam ativas simultaneamente
QUANTIDADE = {"DIARIA": 3, "SEMANAL": 2, "MENSAL": 3}


def _janela(tipo, hoje):
    """Retorna (inicio, fim) do período vigente para o tipo."""
    if tipo == "DIARIA":
        return hoje, hoje
    if tipo == "SEMANAL":
        inicio = hoje - timedelta(days=hoje.weekday())      # segunda desta semana
        return inicio, inicio + timedelta(days=6)           # domingo
    # MENSAL
    inicio = hoje.replace(day=1)
    if inicio.month == 12:
        prox = inicio.replace(year=inicio.year + 1, month=1)
    else:
        prox = inicio.replace(month=inicio.month + 1)
    return inicio, prox - timedelta(days=1)


class Command(BaseCommand):
    help = "Gera missões ativas sorteando moldes (3 diárias, 2 semanais, 3 mensais)."

    def add_arguments(self, parser):
        parser.add_argument("--tipo", choices=["DIARIA", "SEMANAL", "MENSAL"], default=None)
        parser.add_argument("--forcar", action="store_true")

    def handle(self, *args, **opts):
        hoje = timezone.now().date()
        tipos = [opts["tipo"]] if opts["tipo"] else ["DIARIA", "SEMANAL", "MENSAL"]

        for tipo in tipos:
            inicio, fim = _janela(tipo, hoje)

            existentes = MissaoAtiva.objects.filter(
                tipo=tipo, periodo_inicio=inicio, periodo_fim=fim
            )
            if existentes.exists() and not opts["forcar"]:
                self.stdout.write(f"• {tipo}: já há missões para {inicio}→{fim} (pulado)")
                continue
            if opts["forcar"]:
                existentes.delete()

            moldes = list(MoldeMissao.objects.filter(tipo=tipo, ativa=True))
            if not moldes:
                self.stdout.write(self.style.WARNING(f"! {tipo}: nenhum molde ativo cadastrado"))
                continue

            # sorteio ponderado pelo peso, sem repetir molde
            qtd = min(QUANTIDADE[tipo], len(moldes))
            escolhidos = self._sortear_sem_repetir(moldes, qtd)

            for molde in escolhidos:
                meta = random.randint(molde.meta_min, molde.meta_max)
                MissaoAtiva.objects.create(
                    molde=molde, tipo=tipo, gatilho=molde.gatilho,
                    titulo=molde.titulo,
                    descricao=molde.descricao or f"Meta: {meta}",
                    meta_quantidade=meta,
                    recompensa_lc=molde.recompensa_lc,
                    recompensa_xp=molde.recompensa_xp,
                    periodo_inicio=inicio, periodo_fim=fim,
                )
            self.stdout.write(self.style.SUCCESS(
                f"✓ {tipo}: {len(escolhidos)} missões geradas para {inicio}→{fim}"
            ))

    def _sortear_sem_repetir(self, moldes, qtd):
        escolhidos = []
        pool = moldes[:]
        for _ in range(qtd):
            if not pool:
                break
            pesos = [m.peso_sorteio for m in pool]
            m = random.choices(pool, weights=pesos, k=1)[0]
            escolhidos.append(m)
            pool.remove(m)
        return escolhidos