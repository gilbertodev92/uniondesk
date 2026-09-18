# -*- coding: utf-8 -*-
"""
Gera o documento mestre do UnionDesk (especificação + mockups visuais)
Saída: UnionDesk_Documento_Mestre.pdf (A4 vertical)
Requisitos: pip install reportlab matplotlib
"""

import os
from datetime import datetime

# ---------- MOCKUPS (matplotlib) ----------
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, ArrowStyle, FancyArrowPatch

# ---------- PDF (reportlab) ----------
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Table, TableStyle, ListFlowable, ListItem
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# --------------------------------------------------
# CONFIG GERAL
# --------------------------------------------------
OUT_DIR = os.path.abspath(".")
PDF_NAME = "UnionDesk_Documento_Mestre.pdf"
THEME_PRIMARY = "#1e3a8a"  # azul escuro
SUBTLE_TEXT = "#374151"
LIGHT_BG = "#f3f4f6"

IMG_W, IMG_H = 1200, 700  # px para mockups

def ensure_dirs():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR, exist_ok=True)

# --------------------------------------------------
# HELPERS DE UI (MOCKUPS)
# --------------------------------------------------
def ui_canvas(title, subtitle=None):
    fig, ax = plt.subplots(figsize=(IMG_W/100, IMG_H/100))
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 700)
    ax.axis("off")
    # Header
    ax.add_patch(Rectangle((0, 650), 1200, 50, color=THEME_PRIMARY))
    ax.text(20, 675, "UnionDesk · Controle Interno de Chamados",
            va="center", ha="left", color="white", fontsize=14, weight="bold")
    ax.text(1180, 675, "Home  |  Sair", va="center", ha="right", color="white", fontsize=10)
    # Title
    ax.text(20, 625, title, va="center", ha="left", fontsize=14, weight="bold", color=THEME_PRIMARY)
    if subtitle:
        ax.text(20, 605, subtitle, va="center", ha="left", fontsize=10, color=SUBTLE_TEXT)
    # Sidebar
    ax.add_patch(Rectangle((0, 0), 220, 600, color=LIGHT_BG))
    ax.text(20, 570, "Módulos", fontsize=11, weight="bold", color="#111827")
    menu = ["Chamados", "Clientes", "Implantação", "CS", "Base", "Cofre", "Agenda", "Gamificação"]
    for i, item in enumerate(menu):
        y = 540 - i*40
        ax.add_patch(FancyBboxPatch((10, y-18), 200, 28, boxstyle="round,pad=0.02,rounding_size=6",
                                    facecolor="white", edgecolor="#e5e7eb"))
        ax.text(20, y-5, item, fontsize=10, color="#111827")
    return fig, ax

def draw_table(ax, x, y, w, h, cols, rows, headers=None):
    ax.add_patch(FancyBboxPatch((x, y-h), w, h, boxstyle="round,pad=0.01,rounding_size=6",
                                facecolor="white", edgecolor="#e5e7eb"))
    col_w = w/cols
    row_h = h/(rows + (1 if headers else 0))
    if headers:
        for c in range(cols):
            ax.add_patch(Rectangle((x+c*col_w, y - row_h), col_w, row_h, color="#eef2ff"))
            ax.text(x+c*col_w+8, y - row_h/2, headers[c], va="center", ha="left",
                    fontsize=9, color="#111827", weight="bold")
    for r in range(rows):
        for c in range(cols):
            y0 = y - row_h*(r+1 + (1 if headers else 0))
            ax.add_patch(Rectangle((x+c*col_w, y0), col_w, row_h, fill=False, edgecolor="#f3f4f6"))

def gen_mockups():
    imgs = {}

    # 1. Lista de Chamados
    fig, ax = ui_canvas("Chamados Internos", "Painel com filtros, tabela e ações rápidas")
    ax.add_patch(FancyBboxPatch((240, 520), 940, 60, boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor="white", edgecolor="#e5e7eb"))
    ax.text(260, 550, "Buscar...                                 Status  ▼   Prioridade  ▼   Sistema  ▼   Técnico  ▼   Período  ▼",
            fontsize=9, color="#6b7280")

    ax.text(20, 480, "Filtros", fontsize=11, weight="bold", color="#111827")
    sections = [
        ("Status", ["Novo", "Em atendimento", "Implantação", "Pós", "Aguardando Dev", "Encerrado"]),
        ("Prioridade", ["Crítica", "Urgente", "Normal", "Baixa"]),
        ("Sistema", ["ClipPro", "Zucchetti", "Raffinato"])
    ]
    yy = 450
    for title, opts in sections:
        ax.text(20, yy, title, fontsize=10, weight="bold", color=SUBTLE_TEXT); yy -= 20
        for o in opts:
            ax.text(30, yy, f"□ {o}", fontsize=9, color="#111827"); yy -= 18
        yy -= 6
    draw_table(ax, 240, 500, 940, 430, cols=7, rows=8,
               headers=["ID","Cliente","Sistema","Status","Técnico","Prioridade","Atualizado"])
    ax.text(240, 55, "Ações rápidas:  👁️ Ver   🔁 Transferir   ✅ Encerrar   📎 Anexar   💬 Histórico",
            fontsize=9, color=SUBTLE_TEXT)
    imgs["chamados"] = os.path.join(OUT_DIR, "mock_chamados.png")
    fig.savefig(imgs["chamados"], bbox_inches="tight"); plt.close(fig)

    # 2. Detalhe do Chamado
    fig, ax = ui_canvas("Detalhe do Chamado", "Timeline tipo chat com anexos e mudanças de status")
    ax.add_patch(FancyBboxPatch((240, 540), 940, 40, boxstyle="round,pad=0.02,rounding_size=8",
                                facecolor="white", edgecolor="#e5e7eb"))
    ax.text(260, 560, "Cliente: Padaria Jurerê  •  Sistema: ClipPro  •  Status: Em atendimento  •  Prioridade: Urgente  •  Técnico: Letícia", fontsize=9)
    ax.add_patch(FancyBboxPatch((240, 100), 940, 430, boxstyle="round,pad=0.02,rounding_size=8", facecolor="white", edgecolor="#e5e7eb"))

    def bubble(x, y, w, txt, left=True):
        ax.add_patch(FancyBboxPatch((x, y), w, 60, boxstyle="round,pad=0.03,rounding_size=8",
                                    facecolor="#eef2ff" if left else "#f3f4f6", edgecolor="#e5e7eb"))
        ax.text(x+10, y+35, txt, fontsize=9, color="#111827")

    bubble(260, 440, 400, "Cliente: 'Erro ao emitir NFC-e 999: rejeição X'")
    bubble(760, 360, 400, "Técnico Letícia: 'Validado certificado. Ajustando série...'", left=False)
    bubble(260, 280, 500, "Sistema: Status alterado de Novo → Em Atendimento (por Letícia)")
    bubble(760, 200, 360, "Anexo: print_erro.png", left=False)

    ax.add_patch(FancyBboxPatch((240, 40), 940, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(260, 60, "Escreva uma nota técnica...                                      + Anexar   Enviar", fontsize=9, color="#6b7280")
    imgs["detalhe"] = os.path.join(OUT_DIR, "mock_detalhe_chamado.png")
    fig.savefig(imgs["detalhe"], bbox_inches="tight"); plt.close(fig)

    # 3. Implantação
    fig, ax = ui_canvas("Gestão de Implantação", "Checklist técnico e vínculo à agenda")
    ax.add_patch(FancyBboxPatch((240, 540), 940, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(260, 560, "Executora: LógicaMais  •  Cliente: Mercado Jurerê  •  Sistema: ClipPro  •  Data: 10/11/2025 09:00", fontsize=9)

    ax.text(260, 520, "Checklist", fontsize=10, weight="bold", color="#111827")
    checks = ["Sistema instalado", "Base convertida", "Impressoras integradas", "NFCE validada", "Backup Configurado", "Cliente apto a operar"]
    y=500
    for c in checks:
        ax.text(260, y, f"□ {c}", fontsize=9); y -= 22

    ax.text(660, 520, "Módulos treinados", fontsize=10, weight="bold", color="#111827")
    mods = ["Cadastros", "Entrada NF", "Saída NF", "Etiquetas"]
    y=500
    for m in mods:
        ax.text(660, y, f"□ {m}", fontsize=9); y -= 22

    ax.text(900, 520, "Equipamentos", fontsize=10, weight="bold", color="#111827")
    eqs = ["Computador (2) - Suporte", "Impressora (1) - Assistência", "Balança (1) - Suporte"]
    y=500
    for e in eqs:
        ax.text(900, y, f"• {e}", fontsize=9); y -= 22

    ax.add_patch(FancyBboxPatch((240, 80), 200, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor=THEME_PRIMARY))
    ax.text(260, 100, "🗓️ Vincular Agenda", color="white", fontsize=10)
    ax.add_patch(FancyBboxPatch((460, 80), 200, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor=THEME_PRIMARY))
    ax.text(485, 100, "📄 Gerar PDF", color="white", fontsize=10)
    ax.add_patch(FancyBboxPatch((680, 80), 220, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor="#16a34a"))
    ax.text(705, 100, "✅ Concluir Implantação", color="white", fontsize=10)

    imgs["implantacao"] = os.path.join(OUT_DIR, "mock_implantacao.png")
    fig.savefig(imgs["implantacao"], bbox_inches="tight"); plt.close(fig)

    # 4. CS Painel
    fig, ax = ui_canvas("CS – Satisfação do Cliente", "Bot → Humano, notas e pendências")
    cards = [("CSAT Mês", "95%"), ("Tempo 1ª resposta", "18 min"), ("Taxa de resposta", "82%")]
    x=240
    for title, value in cards:
        ax.add_patch(FancyBboxPatch((x, 520), 300, 80, boxstyle="round,pad=0.02,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
        ax.text(x+15, 570, title, fontsize=10, color="#6b7280")
        ax.text(x+15, 545, value, fontsize=18, weight="bold", color="#111827")
        x+=320
    ax.text(240, 500, "Pendentes (nota < 4)", fontsize=10, weight="bold")
    draw_table(ax, 240, 490, 460, 300, cols=3, rows=6, headers=["Cliente","Técnico","Nota"])
    ax.text(720, 500, "Histórico recente", fontsize=10, weight="bold")
    draw_table(ax, 720, 490, 460, 300, cols=3, rows=6, headers=["Cliente","Comentário","Nota"])
    imgs["cs"] = os.path.join(OUT_DIR, "mock_cs.png")
    fig.savefig(imgs["cs"], bbox_inches="tight"); plt.close(fig)

    # 5. Gamificação
    fig, ax = ui_canvas("Gamificação", "Ranking, missões e check-in (passe de batalha)")
    ax.text(240, 520, "Ranking do mês", fontsize=10, weight="bold")
    draw_table(ax, 240, 510, 560, 320, cols=3, rows=8, headers=["Técnico","Pontos","CS médio"])
    ax.text(820, 520, "Check-in diário", fontsize=10, weight="bold")
    ax.add_patch(FancyBboxPatch((820, 250), 360, 260, boxstyle="round,pad=0.02,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    for r in range(5):
        for c in range(7):
            ax.add_patch(Rectangle((840 + c*48, 470 - r*48), 40, 40, edgecolor="#e5e7eb", facecolor="#f9fafb"))
    ax.text(820, 220, "Missões semanais: fechar 15 no SLA | criar 3 artigos | concluir 1 implantação", fontsize=9, color=SUBTLE_TEXT)
    imgs["gamificacao"] = os.path.join(OUT_DIR, "mock_gamificacao.png")
    fig.savefig(imgs["gamificacao"], bbox_inches="tight"); plt.close(fig)

    # 6. CSV
    fig, ax = ui_canvas("Importação CSV de Clientes", "Modelo e validações")
    draw_table(ax, 240, 520, 940, 360, cols=9, rows=10,
               headers=["Nome Fantasia","Razão","CNPJ","IE","Telefone","WhatsApp","Email","Endereço","Sistema"])
    ax.text(240, 145, "Validações: CNPJ/CPF válidos • Email obrigatório • Sistema existente (ou 'Não identificado')", fontsize=9, color=SUBTLE_TEXT)
    ax.add_patch(FancyBboxPatch((240, 80), 220, 40, boxstyle="round,pad=0.02,rounding_size=8", facecolor=THEME_PRIMARY))
    ax.text(260, 100, "⬆️ Enviar CSV", color="white", fontsize=10)
    imgs["csv"] = os.path.join(OUT_DIR, "mock_csv.png")
    fig.savefig(imgs["csv"], bbox_inches="tight"); plt.close(fig)

    # 7. Permissões
    fig, ax = ui_canvas("Matriz de Permissões", "Perfis e escopos de acesso")
    draw_table(ax, 240, 520, 940, 360, cols=7, rows=6,
               headers=["Função","Abrir","Editar","Transferir","Encerrar","Ver setor","Ver todos"])
    ax.text(240, 145, "Regras: Gestor (total no setor) • Técnico (próprios + fila setor) • Comercial (implantação) • CS (pós)", fontsize=9, color=SUBTLE_TEXT)
    imgs["permissoes"] = os.path.join(OUT_DIR, "mock_permissoes.png")
    fig.savefig(imgs["permissoes"], bbox_inches="tight"); plt.close(fig)

    # 8. Fluxo Bot
    fig, ax = ui_canvas("Fluxo Bot (Evolution + n8n + UnionDesk)", "Do WhatsApp ao CS humano")
    ax.add_patch(FancyBboxPatch((300, 520), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(410, 555, "Cliente", ha="center", fontsize=10)
    ax.add_patch(FancyBboxPatch((570, 520), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(680, 555, "Evolution", ha="center", fontsize=10)
    ax.add_patch(FancyBboxPatch((840, 520), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(950, 555, "UnionDesk Webhook", ha="center", fontsize=10)
    ax.add_patch(FancyArrowPatch((520, 555), (570, 555), arrowstyle=ArrowStyle("->", head_length=6, head_width=3),
                                 mutation_scale=12, color="#111827"))
    ax.add_patch(FancyArrowPatch((790, 555), (840, 555), arrowstyle=ArrowStyle("->", head_length=6, head_width=3),
                                 mutation_scale=12, color="#111827"))

    ax.add_patch(FancyBboxPatch((300, 380), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(410, 415, "Classificador IA", ha="center", fontsize=10)
    ax.add_patch(FancyBboxPatch((570, 380), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(680, 415, "Regras de Prioridade", ha="center", fontsize=10)
    ax.add_patch(FancyBboxPatch((840, 380), 220, 70, boxstyle="round,pad=0.03,rounding_size=10", facecolor="white", edgecolor="#e5e7eb"))
    ax.text(950, 415, "Fila do Setor", ha="center", fontsize=10)
    ax.add_patch(FancyArrowPatch((520, 415), (570, 415), arrowstyle=ArrowStyle("->", head_length=6, head_width=3),
                                 mutation_scale=12, color="#111827"))
    ax.add_patch(FancyArrowPatch((790, 415), (840, 415), arrowstyle=ArrowStyle("->", head_length=6, head_width=3),
                                 mutation_scale=12, color="#111827"))

    ax.text(240, 330, "Se 3 interações sem solução → oferecer humano automaticamente", fontsize=9, color=SUBTLE_TEXT)
    imgs["fluxo"] = os.path.join(OUT_DIR, "mock_fluxo_bot.png")
    fig.savefig(imgs["fluxo"], bbox_inches="tight"); plt.close(fig)

    return imgs

# --------------------------------------------------
# PDF BUILDER
# --------------------------------------------------
def build_pdf(imgs):
    pdf_path = os.path.join(OUT_DIR, PDF_NAME)
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            leftMargin=1.6*cm, rightMargin=1.6*cm, topMargin=1.6*cm, bottomMargin=1.6*cm)
    styles = getSampleStyleSheet()
    H1 = ParagraphStyle(name="H1", parent=styles["Heading1"], textColor=colors.HexColor(THEME_PRIMARY))
    H2 = ParagraphStyle(name="H2", parent=styles["Heading2"], textColor=colors.HexColor(THEME_PRIMARY))
    H3 = ParagraphStyle(name="H3", parent=styles["Heading3"], textColor=colors.HexColor(THEME_PRIMARY))
    BODY = styles["Normal"]

    E = []

    # CAPA
    E.append(Paragraph("<b>UnionDesk – Documento Mestre de Especificação e Mockups</b>", H1))
    E.append(Spacer(1, 6))
    E.append(Paragraph("Relatório técnico completo com regras funcionais, fluxos e simulações visuais de telas.", BODY))
    E.append(Spacer(1, 12))
    E.append(Paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y')}", BODY))
    E.append(Spacer(1, 24))
    E.append(Paragraph("<b>Identidade visual:</b> azul-escuro (#1e3a8a) + branco; layout técnico moderno.", BODY))
    E.append(PageBreak())

    # SUMÁRIO (manual, simples)
    E.append(Paragraph("Sumário", H2))
    toc_rows = [
        ["1.", "Especificação Funcional (Decisões e Regras)"],
        ["2.", "Mockups Visuais (Telas e Fluxos)"],
    ]
    toc_tbl = Table(toc_rows, colWidths=[30, 450])
    toc_tbl.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor("#eef2ff"))]))
    E.append(Spacer(1, 6))
    E.append(toc_tbl)
    E.append(PageBreak())

    # -------------------------
    # 1. ESPECIFICAÇÃO FUNCIONAL
    # -------------------------
    E.append(Paragraph("1. Especificação Funcional – Decisões e Regras", H1))

    # 1.1 Chamados
    E.append(Paragraph("1.1 Chamados (Atendimentos Internos)", H2))
    E.append(Paragraph("Status únicos: Novo, Em atendimento, Em implantação, Pós implantação, Aguardando Desenvolvimento, Encerrado.", BODY))
    bullet1 = [
        "Se o cliente tem chamado aberto (≠ Encerrado), o sistema avisa e oferece anexar. Anexo respeita o setor.",
        "Transições registradas no histórico: status, data/hora, autor.",
        "Encerramento: Motivo (obrigatório) + Observação final (obrigatório).",
        "Motivos (catálogo): Arquivos Fiscais; Certificado Digital; Engano/Não precisa mais; Inatividade; Atualização; Contabilidade; Dúvidas com Notas; Dúvidas com Software; Erros Fiscais; Financeiro; Implantação; Migração Tributária; Orçamentos; Hardware; SEFAZ; Bug Sistema; TEF Oscilando; Retornar mais tarde.",
        "Reabertura: somente Admin Suporte ou Admin Comercial.",
        "One-touch detectado automaticamente (sem marca manual).",
        "Transferência registra histórico e notifica in-app.",
    ]
    E.append(ListFlowable([ListItem(Paragraph(x, BODY)) for x in bullet1], bulletType='bullet'))
    E.append(Spacer(1, 6))

    # SLA
    E.append(Paragraph("SLA e Prioridade", H3))
    sla_tbl = Table([
        ["Prioridade", "Atendimento inicial", "Solução"],
        ["Crítica (sistema parado)", "15 min (úteis) após assumir", "1h30 (úteis)"],
        ["Urgente", "30 min (úteis) após assumir", "2h30 (úteis)"],
        ["Normal", "8h úteis", "24h úteis"],
        ["Baixa/Melhoria", "24h úteis", "5 dias úteis (ou sem prazo)"],
    ], colWidths=[150,170,170])
    sla_tbl.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor("#eef2ff"))]))
    E.append(sla_tbl)
    E.append(Paragraph("Contagem inicia quando o Suporte assume o chamado. Horas úteis: seg–sex, 08:00–18:00, com feriados cadastrados.", BODY))
    E.append(Spacer(1, 6))

    # Notificações
    E.append(Paragraph("Notificações in-app", H3))
    bullet2 = [
        "Pessoal (atribuído/transferido para mim).",
        "Setor (novo chamado na fila).",
        "Alerta (SLA >80%, CS ruim, reabertura).",
        "Silenciamento por usuário (1h / até amanhã)."
    ]
    E.append(ListFlowable([ListItem(Paragraph(x, BODY)) for x in bullet2], bulletType='bullet'))
    E.append(PageBreak())

    # 1.2 Clientes
    E.append(Paragraph("1.2 Clientes", H2))
    E.append(Paragraph("Campos: Nome/Fantasia, Razão, CNPJ/CPF, IE, Responsável, Telefone, WhatsApp, E-mail, Endereço, Sistemas (múltiplos).", BODY))
    E.append(Paragraph("Flags: possui contrato de software; possui contrato de assistência. Sem contrato: obrigatório Valor + Aprovado por quem.", BODY))
    E.append(Paragraph("Importação CSV (misto): se CNPJ existe → atualiza e adiciona contato novo; senão → cria. Valida CNPJ/CPF, e-mail e sistema.", BODY))

    # 1.3 Histórico
    E.append(Paragraph("1.3 Histórico do Chamado (Timeline)", H2))
    E.append(Paragraph("Chat técnico único: mensagens, anexos, mudança de status, transferências, bot e CS. Sem edição.", BODY))
    E.append(Paragraph("Limites de anexo: 1 GB por chamado (soma) e 200 MB por arquivo. Armazenamento S3 compatível.", BODY))

    # 1.4 Implantação
    E.append(Paragraph("1.4 Implantação e Treinamentos", H2))
    E.append(Paragraph("Implantação é tipo especial de chamado com campos extras e vínculo à agenda. Comercial abre; Suporte conclui.", BODY))
    E.append(Paragraph("Checklist com PDF técnico (assinatura em papel). Vincular evento; remarcação/troca de técnico reflete no chamado.", BODY))
    E.append(PageBreak())

    # 1.5 CS
    E.append(Paragraph("1.5 CS – Satisfação do Cliente", H2))
    E.append(Paragraph("Disparo automático para Urgente/Crítica e Implantação/Treinamento. Nota 1–5 + comentário; CS pendente se 72h sem resposta.", BODY))
    E.append(Paragraph("Painel: CSAT mensal, média por técnico, taxa de resposta, pendências.", BODY))

    # 1.6 Bot
    E.append(Paragraph("1.6 Chatbot (Evolution + n8n + UnionDesk)", H2))
    E.append(Paragraph("Regras críticas no Union; IA para intenção/extração; n8n para orquestrar webhooks e alertas. Protocolo ATD-AAAA-NNNNNN.", BODY))
    E.append(Paragraph("Rascunho de chamado antes do humano. Gatilhos: sem emitir NF, sistema parado, erro SEFAZ/SAT/NFC-e, TEF fora.", BODY))

    # 1.7 Base + Cofre
    E.append(Paragraph("1.7 Base de Conhecimento e Cofre de Senhas", H2))
    E.append(Paragraph("Base: artigos internos com anexos e links de chamados. Cofre: segredos por cliente com criptografia e máscara parcial.", BODY))
    E.append(Paragraph("Relevância automática: Base (10 views únicas OU 3 chamados linkados OU 5 'Útil' em 30d → +12); Edição relevante +6; Cofre: +5/+3; Duplicado: −5.", BODY))
    E.append(PageBreak())

    # 1.8 Gamificação
    E.append(Paragraph("1.8 Gamificação", H2))
    E.append(Paragraph("Ranking mensal; temporadas 6 meses; check-in diário (passe de batalha) com streaks e missões semanais; checkpoints (500/1000/2000).", BODY))
    g_tbl = Table([
        ["Ação","Pontos"],
        ["Fechar chamado (dentro SLA)","+10"],
        ["Fechar chamado (fora SLA)","+4"],
        ["Nota CS ≥ 4","+6"],
        ["Implantação concluída","+60 (divide entre envolvidos)"],
        ["Artigo relevante","+12"],
        ["Edição relevante","+6"],
        ["Cofre relevante","+5"],
        ["SLA estourado","−6"],
        ["Chamado reaberto","−8"],
        ["CS ruim (≤ 2)","−10"],
    ], colWidths=[300,140])
    g_tbl.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor("#eef2ff"))]))
    E.append(g_tbl)
    E.append(Paragraph("Limite diário: 100 pts (exibir no painel). Sub-limites: Base 40/dia; Cofre 30/dia. Check-in diário obrigatório para prêmios.", BODY))
    E.append(PageBreak())

    # 1.9 Agenda/Operação
    E.append(Paragraph("1.9 Agenda, Segurança e Operação", H2))
    E.append(Paragraph("Agenda: guarda data/hora/título/observações/responsável; chamado guarda ID do evento; atalho 'Abrir na Agenda'.", BODY))
    bullet3 = [
        "Permissões: Admin; Gestor de Setor; Técnico; Comercial; CS.",
        "Auditoria por app (assumir/transferir, status/prioridade, reabrir/encerrar; Base/Cofre; gamificação).",
        "Armazenamento de anexos: S3 c/ versionamento e lifecycle. Retenção: 24 meses.",
        "Backups: banco diário + WAL; observabilidade + alertas via n8n.",
        "Feature flags: Chamados → Implantação → CS → Gamificação → Bot."
    ]
    E.append(ListFlowable([ListItem(Paragraph(x, BODY)) for x in bullet3], bulletType='bullet'))
    E.append(PageBreak())

    # -------------------------
    # 2. MOCKUPS VISUAIS
    # -------------------------
    E.append(Paragraph("2. Mockups Visuais (página inteira)", H1))
    E.append(Spacer(1, 8))

    for key in ["chamados","detalhe","implantacao","cs","gamificacao","csv","permissoes","fluxo"]:
        img_path = imgs[key]
        E.append(RLImage(img_path, width=18*cm, height=10.5*cm))
        E.append(PageBreak())

    # Rodapé padrão (o SimpleDocTemplate não tem rodapé fixo simples; manteremos conteúdo limpo)
    doc.build(E)
    return pdf_path

def main():
    ensure_dirs()
    imgs = gen_mockups()
    pdf_path = build_pdf(imgs)
    print(f"OK! Gerado: {pdf_path}")

if __name__ == "__main__":
    main()
