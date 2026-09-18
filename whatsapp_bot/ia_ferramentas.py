# /whatsapp_bot/ia_ferramentas.py
import re
from crm_vendas.models import Lead # Já ajustado com o nome do seu app

def processar_comando_lead(comando_texto, telefone_cliente):
    """
    Lê a tag secreta da IA no formato: Nome Empresa | Nome Contato | Dor Principal
    E salva direto no banco do CRM.
    """
    partes = [p.strip() for p in comando_texto.split('|')]
    
    if len(partes) >= 3:
        empresa = partes[0]
        contato = partes[1]
        dor = partes[2]
    else:
        empresa = partes[0] if len(partes) > 0 else "Não Informado pela IA"
        contato = "Contato WhatsApp"
        dor = comando_texto

    # 🔥 A MÁGICA DA OBSERVAÇÃO AQUI
    dor_final = f"{dor}\n\n(Lead Gerado pela IA no Whatsapp, Cliente está no bot aguardando atendimento)"

    telefone_limpo = re.sub(r'\D', '', str(telefone_cliente))
    
    # Trava de Segurança: Evita criar lead duplicado
    etapas_ativas = ['0_PROSPECCAO', '1_LEAD', '2_CONTATO', '3_DIAGNOSTICO', '4_PROPOSTA', '5_NEGOCIACAO']
    if Lead.objects.filter(telefone__icontains=telefone_limpo, etapa__in=etapas_ativas).exists():
        return 
    
    try:
        Lead.objects.create(
            nome_empresa=empresa,
            nome_contato=contato,
            telefone=telefone_limpo,
            cidade="Capturado via WhatsApp",
            origem='WHATSAPP',
            etapa='1_LEAD',
            dor_principal=dor_final,
            observacao_rapida="🤖 [LEAD TRIADO E ABERTO PELA IA]"
        )
        print(f"✅ Lead {empresa} criado com sucesso pela IA!")
    except Exception as e:
        print(f"[ERRO IA CRM] Falha ao criar lead: {e}")