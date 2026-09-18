"""
Popula os itens colecionáveis iniciais com a economia já calibrada.

Uso:  python manage.py popular_recompensas

Cria (se ainda não existirem):
- Home Office (Comum),   3 peças, desenc +8  / craft -28
- Pack de XP  (Raro),    4 peças, desenc +20 / craft -70
- Day Off     (Épico),   6 peças, desenc +60 / craft -210
- Headset     (Lendário),8 peças, desenc +130/ craft -455

E as faces da roleta (peças), com peso maior para itens comuns.
"""
from django.core.management.base import BaseCommand
from recompensas.models import ItemColecionavel, PecaRoleta, ItemLojaOficial, MoldeMissao


# ── Moldes de missão (o gerador sorteia destes) ──
# Cada molde vira várias missões diferentes ao longo do tempo, com meta
# variando entre meta_min e meta_max. Recompensa cresce com o tipo.
MOLDES = [
    # DIÁRIAS (rápidas, recompensa modesta)
    ("DIARIA", "Maratona de Atendimentos", "fechar_chamado", 3, 6, 30, 15, 3),
    ("DIARIA", "Resolvedor do Bot", "finalizar_chat", 4, 8, 25, 12, 3),
    ("DIARIA", "Voz dos Grupos", "responder_grupo", 5, 12, 20, 10, 2),
    ("DIARIA", "Cuidando do Cliente", "registrar_contato_cs", 2, 4, 35, 18, 2),
    ("DIARIA", "Estrela do Dia", "feedback_5_estrelas", 1, 2, 40, 20, 2),
    ("DIARIA", "Documentador", "cadastrar_base_conhecimento", 1, 2, 25, 12, 1),

    # SEMANAIS (mais esforço, recompensa média)
    ("SEMANAL", "Força-Tarefa Semanal", "fechar_chamado", 20, 35, 150, 80, 3),
    ("SEMANAL", "Rei do WhatsApp", "finalizar_chat", 25, 45, 140, 75, 3),
    ("SEMANAL", "Guardião dos Grupos", "finalizar_grupo", 15, 30, 130, 70, 2),
    ("SEMANAL", "Retenção em Foco", "registrar_contato_cs", 8, 15, 160, 90, 2),
    ("SEMANAL", "Colecionador de Estrelas", "feedback_5_estrelas", 5, 10, 180, 100, 2),

    # MENSAIS (maratona, recompensa alta)
    ("MENSAL", "Lenda do Mês", "fechar_chamado", 80, 130, 600, 350, 3),
    ("MENSAL", "Mestre do Bot", "finalizar_chat", 100, 160, 580, 340, 3),
    ("MENSAL", "Herói da Retenção", "registrar_contato_cs", 30, 50, 650, 400, 2),
    ("MENSAL", "Impecável", "feedback_5_estrelas", 20, 40, 700, 420, 2),
    ("MENSAL", "Enciclopédia Viva", "cadastrar_base_conhecimento", 8, 15, 500, 300, 1),
]


ITENS = [
    {
        "nome": "Home Office", "raridade": "COMUM", "total_pecas": 3,
        "po_ao_desencantar": 8, "po_para_craftar": 28,
        "icone": "fa-house-laptop", "efeito": "HOME_OFFICE",
        "descricao": "1 dia de trabalho remoto.", "peso_roleta": 40,
    },
    {
        "nome": "Pack de XP", "raridade": "RARO", "total_pecas": 4,
        "po_ao_desencantar": 20, "po_para_craftar": 70,
        "icone": "fa-bolt", "efeito": "PACK_XP", "valor_efeito": 500,
        "descricao": "Turbo de 500 XP no seu perfil.", "peso_roleta": 22,
    },
    {
        "nome": "Day Off", "raridade": "EPICO", "total_pecas": 6,
        "po_ao_desencantar": 60, "po_para_craftar": 210,
        "icone": "fa-umbrella-beach", "efeito": "DAY_OFF",
        "descricao": "Um dia de folga. Épico — some só a cada ~6 meses.", "peso_roleta": 8,
    },
    {
        "nome": "Headset Gamer", "raridade": "LENDARIO", "total_pecas": 8,
        "po_ao_desencantar": 130, "po_para_craftar": 455,
        "icone": "fa-headset", "efeito": "FISICO",
        "descricao": "Headset gamer de verdade. O troféu supremo — mais de 1 ano juntando.", "peso_roleta": 3,
    },
]


class Command(BaseCommand):
    help = "Popula itens colecionáveis, faces da roleta e loja oficial (economia calibrada)."

    def handle(self, *args, **options):
        for dados in ITENS:
            peso = dados.pop("peso_roleta")
            item, criado = ItemColecionavel.objects.get_or_create(
                nome=dados["nome"], defaults=dados
            )
            if criado:
                self.stdout.write(self.style.SUCCESS(f"✓ Item criado: {item.nome}"))
                # cria as faces da roleta (uma por peça do item)
                for n in range(1, item.total_pecas + 1):
                    PecaRoleta.objects.create(item=item, numero_peca=n, peso_sorteio=peso)
                self.stdout.write(f"  + {item.total_pecas} faces de roleta (peso {peso})")
            else:
                self.stdout.write(self.style.WARNING(f"• Já existe: {item.nome} (pulado)"))

        # Home Office também na loja oficial, por LC
        ho, criado = ItemLojaOficial.objects.get_or_create(
            nome="Home Office (Loja)",
            defaults={
                "descricao": "1 dia de trabalho remoto. Comprado direto por Lógica Coins.",
                "preco_lc": 50, "icone": "fa-house-laptop",
            },
        )
        if criado:
            self.stdout.write(self.style.SUCCESS("✓ Home Office na loja oficial (50 LC)"))

        # ── Moldes de missão ──
        criados_moldes = 0
        for tipo, titulo, gatilho, mmin, mmax, lc, xp, peso in MOLDES:
            molde, criado = MoldeMissao.objects.get_or_create(
                titulo=titulo, tipo=tipo,
                defaults={
                    "gatilho": gatilho, "meta_min": mmin, "meta_max": mmax,
                    "recompensa_lc": lc, "recompensa_xp": xp, "peso_sorteio": peso,
                    "descricao": "",
                },
            )
            if criado:
                criados_moldes += 1
        self.stdout.write(self.style.SUCCESS(f"✓ {criados_moldes} moldes de missão criados"))

        self.stdout.write(self.style.SUCCESS("\nPronto! Economia calibrada carregada."))
        self.stdout.write("Ajuste pesos/custos no admin quando quiser.")
        self.stdout.write("Agora rode: python manage.py gerar_missoes")