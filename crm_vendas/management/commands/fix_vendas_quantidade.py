"""
Comando de correção retroativa: vendas lançadas com valor UNITÁRIO
em vez de valor x quantidade (bug corrigido em views.py - fechamento GANHO).

ONDE COLOCAR ESTE ARQUIVO:
  crm_vendas/management/commands/fix_vendas_quantidade.py

(crie as pastas "management" e "management/commands" dentro do app crm_vendas,
cada uma com um arquivo vazio __init__.py, se ainda não existirem)

COMO RODAR:
  1) FAÇA BACKUP DO BANCO ANTES DE QUALQUER COISA.
  2) Simulação (não altera nada, só mostra o que seria feito):
       python manage.py fix_vendas_quantidade --dry-run --csv relatorio_dryrun.csv
  3) Revise o relatório e a lista de "não encontrados" / "ambíguos".
  4) Rode de verdade:
       python manage.py fix_vendas_quantidade --csv relatorio_final.csv
"""

import csv
from django.core.management.base import BaseCommand
from crm_vendas.models import ItemProposta, VendaPessoal


class Command(BaseCommand):
    help = (
        "Corrige registros de VendaPessoal criados com o valor unitário do "
        "ItemProposta em vez de valor x quantidade (bug do fechamento GANHO)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas mostra o que seria alterado, sem salvar nada no banco.',
        )
        parser.add_argument(
            '--csv',
            type=str,
            default=None,
            help='Caminho de um arquivo .csv para salvar o relatório das correções.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        csv_path = options.get('csv')

        # Só nos interessam itens com quantidade > 1 de leads que foram GANHOS
        itens_com_qtd = ItemProposta.objects.filter(
            quantidade__gt=1,
            lead__etapa='6_GANHO',
        ).select_related('lead', 'lead__vendedor_responsavel')

        total_itens = itens_com_qtd.count()
        corrigidos = 0
        ja_corretos = 0
        nao_encontrados = []
        ambiguos = []
        linhas_relatorio = []

        for item in itens_com_qtd:
            lead = item.lead
            vendedor = lead.vendedor_responsavel

            if not vendedor:
                nao_encontrados.append((lead, item, 'lead sem vendedor_responsavel'))
                continue

            descricao_esperada = f"{lead.nome_empresa} - {item.nome}"[:200]
            data_venda = lead.data_fechamento.date() if lead.data_fechamento else None

            candidatos_qs = VendaPessoal.objects.filter(
                vendedor=vendedor,
                descricao=descricao_esperada,
            )
            if data_venda:
                candidatos_qs = candidatos_qs.filter(data_venda=data_venda)

            candidatos = list(candidatos_qs)

            if not candidatos:
                nao_encontrados.append((lead, item, 'nenhuma venda correspondente encontrada'))
                continue

            if len(candidatos) > 1:
                # Tenta desempatar: sobra só quem bate com valor unitário (bug) ou subtotal (já certo)
                candidatos = [
                    v for v in candidatos
                    if v.valor == item.valor or v.valor == item.subtotal
                ]
                if len(candidatos) != 1:
                    ambiguos.append((lead, item, candidatos_qs))
                    continue

            venda = candidatos[0]

            if venda.valor == item.subtotal:
                ja_corretos += 1
                continue

            if venda.valor == item.valor:
                linhas_relatorio.append([
                    lead.nome_empresa, item.nome, item.quantidade,
                    str(venda.valor), str(item.subtotal), venda.id,
                ])
                self.stdout.write(
                    f"[{'SIMULADO' if dry_run else 'CORRIGIDO'}] "
                    f"{lead.nome_empresa} - {item.nome}: "
                    f"R$ {venda.valor} -> R$ {item.subtotal}"
                )
                if not dry_run:
                    venda.valor = item.subtotal
                    venda.save(update_fields=['valor'])
                corrigidos += 1
            else:
                # Valor não bate nem com unitário nem com subtotal: melhor não mexer sozinho
                ambiguos.append((lead, item, candidatos_qs))

        self.stdout.write(self.style.SUCCESS(
            f"\nTotal de itens com quantidade > 1 (leads ganhos): {total_itens}\n"
            f"Já estavam corretos: {ja_corretos}\n"
            f"Corrigidos{' (simulação)' if dry_run else ''}: {corrigidos}\n"
            f"Não encontrados: {len(nao_encontrados)}\n"
            f"Ambíguos / revisar manualmente: {len(ambiguos)}\n"
        ))

        if nao_encontrados:
            self.stdout.write(self.style.WARNING("\n--- NÃO ENCONTRADOS (revisar manualmente) ---"))
            for lead, item, motivo in nao_encontrados:
                self.stdout.write(f"  Empresa: {lead.nome_empresa} | Item: {item.nome} | Motivo: {motivo}")

        if ambiguos:
            self.stdout.write(self.style.WARNING("\n--- AMBÍGUOS (revisar manualmente) ---"))
            for lead, item, candidatos_qs in ambiguos:
                candidatos_info = [(v.id, str(v.valor)) for v in candidatos_qs]
                self.stdout.write(
                    f"  Empresa: {lead.nome_empresa} | Item: {item.nome} | "
                    f"Candidatos (id, valor): {candidatos_info}"
                )

        if csv_path:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['empresa', 'item', 'quantidade', 'valor_antigo', 'valor_novo', 'venda_id'])
                writer.writerows(linhas_relatorio)
            self.stdout.write(self.style.SUCCESS(f"\nRelatório salvo em: {csv_path}"))
