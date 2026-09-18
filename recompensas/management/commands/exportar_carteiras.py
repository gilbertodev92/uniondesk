"""
Salva o saldo atual das carteiras num arquivo JSON, ANTES de recriar o schema.

IMPORTANTE: lê direto do banco via SQL cru (não pelo model do Django), porque
neste momento o models.py já tem campos novos (po_magico) que ainda NÃO existem
na tabela real. Ler pelo model daria erro "column does not exist".

Uso:  python manage.py exportar_carteiras
Gera: carteiras_backup.json na raiz do projeto.
"""
import json
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Exporta saldo/XP das carteiras (via SQL cru) para carteiras_backup.json"

    def handle(self, *args, **opts):
        # Descobre quais colunas a tabela REAL tem (pra não pedir po_magico etc.)
        with connection.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'recompensas_carteira'
            """)
            colunas_reais = {row[0] for row in cur.fetchall()}

        # colunas que queremos, SE existirem na tabela real
        desejadas = ["usuario_id", "saldo_moedas", "xp_total", "nivel_atual", "ofensiva_diaria"]
        usar = [c for c in desejadas if c in colunas_reais]

        if "usuario_id" not in usar:
            self.stdout.write(self.style.ERROR("Tabela recompensas_carteira não tem usuario_id? Abortando."))
            return

        col_sql = ", ".join(usar)
        with connection.cursor() as cur:
            cur.execute(f"SELECT {col_sql} FROM recompensas_carteira")
            linhas = cur.fetchall()
            # pega o username de cada usuario_id
            cur.execute("SELECT id, username FROM auth_user")
            nomes = {row[0]: row[1] for row in cur.fetchall()}

        dados = []
        for linha in linhas:
            registro = dict(zip(usar, linha))
            registro["username"] = nomes.get(registro["usuario_id"], f"user_{registro['usuario_id']}")
            # garante os campos mesmo se a coluna não existia
            registro.setdefault("ofensiva_diaria", 0)
            registro.setdefault("nivel_atual", 1)
            dados.append(registro)

        with open("carteiras_backup.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

        self.stdout.write(self.style.SUCCESS(
            f"✓ {len(dados)} carteiras salvas em carteiras_backup.json"
        ))
        for d in dados:
            total = d.get("saldo_moedas", 0) + d.get("xp_total", 0)
            self.stdout.write(f"  {d['username']:15} moedas={d.get('saldo_moedas',0):>7} xp={d.get('xp_total',0):>7} (total {total})")