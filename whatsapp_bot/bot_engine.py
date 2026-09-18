import requests
import json
import re
import logging # 🔥 NOVO: Módulo de Caixa Preta
from django.utils import timezone
from .models import BotConfig, Message
from datetime import timedelta

# 🔥 CONFIGURANDO O RASTREADOR (CAIXA PRETA)
logger = logging.getLogger('rastreador_zap')

def a_empresa_esta_aberta():
    config = BotConfig.objects.first()
    if not config: return True
    agora = timezone.localtime(timezone.now())
    dia_semana = agora.weekday()
    hora_atual = agora.time()
    if dia_semana == 6: return False
    if dia_semana == 5:
        return config.horario_inicio_sabado <= hora_atual <= config.horario_fim_sabado
    return config.horario_inicio_semana <= hora_atual <= config.horario_fim_semana

def descobrir_modelo_valido(api_key):
    # O modelo agora vem do BotConfig (campo 'modelo_ia'), configurável no admin
    # sem mexer em código. Se o campo estiver vazio ou a migration ainda não
    # tiver rodado, cai no padrão gemini-flash-latest (Flash estável mais novo).
    padrao = "models/gemini-flash-latest"
    try:
        config = BotConfig.objects.first()
        nome = (getattr(config, "modelo_ia", "") or "").strip() if config else ""
        if nome:
            # aceita tanto "gemini-flash-latest" quanto "models/gemini-flash-latest"
            return nome if nome.startswith("models/") else f"models/{nome}"
    except Exception as e:
        print(f"[MODELO IA] Falha ao ler modelo do BotConfig, usando padrão: {e}", flush=True)
    return padrao

def chamar_gemini_rest(api_key, prompt, base64_media=None, mime_type=None):
    # CÉREBRO 1: Ouve e Lê (Retorna apenas texto)
    modelo_correto = descobrir_modelo_valido(api_key)
    url = f"https://generativelanguage.googleapis.com/v1beta/{modelo_correto}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    parts = [{"text": prompt}]
    
    if base64_media and mime_type:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64_media}})
        
    payload = {
        "contents": [{"parts": parts}], 
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500}
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200: 
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        else: 
            print(f"\n[ERRO GEMINI TEXTO] {res.text}\n", flush=True)
    except Exception as e:
        print(f"\n[ERRO CONEXAO] {e}\n", flush=True)
    return None

def chamar_gemini_json(api_key, prompt, base64_media=None, mime_type=None):
    """
    CÉREBRO ESTRUTURADO: em vez de devolver uma redação com tags escondidas
    ([SUPORTE], [CRIAR_LEAD]...) pra gente caçar com regex, a IA devolve JSON.
    O raciocínio dela vira DADO, não texto a ser adivinhado.

    Retorna dict (já parseado) ou None se falhar.
    """
    modelo_correto = descobrir_modelo_valido(api_key)
    url = f"https://generativelanguage.googleapis.com/v1beta/{modelo_correto}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    parts = [{"text": prompt}]

    if base64_media and mime_type:
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64_media}})

    # Schema: obriga a IA a responder EXATAMENTE nestes campos.
    schema = {
        "type": "OBJECT",
        "properties": {
            "resposta_cliente": {
                "type": "STRING",
                "description": "O texto que será enviado ao cliente no WhatsApp. Sem tags, sem colchetes."
            },
            "acao": {
                "type": "STRING",
                "enum": ["responder", "transferir", "encerrar", "silencio"],
                "description": "responder=continuar a conversa; transferir=mandar pra fila humana; encerrar=finalizar; silencio=nao responder nada."
            },
            "setor": {
                "type": "STRING",
                "enum": ["SUPORTE", "ASSISTENCIA", "COMERCIAL", "FINANCEIRO", "NENHUM"],
                "description": "Preencha SOMENTE quando acao=transferir. Caso contrario use NENHUM."
            },
            "confianca": {
                "type": "NUMBER",
                "description": "0.0 a 1.0. Sua certeza REAL de que a resposta resolve o caso do cliente. Seja honesta: se nao tem a informacao na base, use valor baixo."
            },
            "criar_lead": {
                "type": "STRING",
                "description": "Somente em caso de venda: 'Empresa | Nome do contato | Dor principal'. Caso contrario deixe vazio."
            }
        },
        "required": ["resposta_cliente", "acao", "confianca"]
    }

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1500,
            "responseMimeType": "application/json",
            "responseSchema": schema,
        }
    }
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            texto = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(texto)
        else:
            print(f"\n[ERRO GEMINI JSON] {res.text}\n", flush=True)
            logger.error(f"[GEMINI JSON] Status {res.status_code}: {str(res.text)[:200]}")
    except json.JSONDecodeError as e:
        logger.error(f"[GEMINI JSON] IA devolveu JSON inválido: {e}")
    except Exception as e:
        print(f"\n[ERRO CONEXAO JSON] {e}\n", flush=True)
        logger.error(f"[GEMINI JSON] Falha de conexão: {e}")
    return None


# Abaixo desta confiança, a IA NÃO deve afirmar nada — ou pergunta, ou transfere.
LIMIAR_CONFIANCA = 0.60


IDENTIDADE_PADRAO = (
    "A Lógica é especialista em AUTOMAÇÃO COMERCIAL. Nós VENDEMOS SISTEMAS e TAMBÉM "
    "VENDEMOS EQUIPAMENTOS FÍSICOS (Bobinas, Leitores de Código de Barras, Impressoras "
    "Térmicas, Computadores, Monitores, Balanças, etc.). Se o cliente perguntar se "
    "vendemos equipamentos, a resposta é SEMPRE SIM."
)

REGRAS_PADRAO = (
    "- Boleto do CLIENTE (emitir/cancelar no sistema dele): é dúvida de suporte "
    "(setor SUPORTE).\n"
    "- 2ª via de boleto DA LÓGICA para clientes RAFFINATO: passe este link direto: "
    "https://painel.prontoparaservir.com.br/segundaviaboleto\n"
    "- 2ª via de boleto DA LÓGICA para outros sistemas: transfira com setor=FINANCEIRO."
)

# Exemplos valem mais que adjetivos: mostram o TOM e o RACIOCÍNIO esperados.
# Tom da casa: parceria — respeitoso, empático, sem informalidade forçada.
EXEMPLOS_PADRAO = """
EXEMPLO 1 — relato vago: investigue antes de agir
Cliente: "tô com problema aqui"
Você: {"resposta_cliente": "Poxa, vamos resolver isso. Me conta um pouco mais: em
qual sistema está acontecendo e qual mensagem aparece na tela?", "acao": "responder",
"setor": "NENHUM", "criar_lead": "", "confianca": 0.75}

EXEMPLO 2 — a base tem a resposta: resolva junto, sem pressa
Cliente: "a impressora puxa o papel mas sai tudo branco"
Você: {"resposta_cliente": "Esse é clássico e costuma ser simples: a bobina está do
lado avesso. Faz o seguinte:\\n\\n1. Abra a tampa da impressora\\n2. Tire a bobina e
vire ela ao contrário\\n3. Feche a tampa e imprima um teste\\n\\nO lado que imprime é
o de fora do rolo. Testa aí e me diz se resolveu.", "acao": "responder",
"setor": "NENHUM", "criar_lead": "", "confianca": 0.95}

EXEMPLO 3 — não sei: transfira com honestidade, sem inventar
Cliente: "preciso alterar o CNPJ da empresa no sistema"
Você: {"resposta_cliente": "Essa alteração mexe no cadastro fiscal e precisa de um
acesso mais avançado, então vou te encaminhar para o Suporte Técnico fazer isso com
segurança. Estamos com bastante procura hoje, pode haver uma pequena espera — mas já
deixei tudo registrado para o técnico.", "acao": "transferir", "setor": "SUPORTE",
"criar_lead": "", "confianca": 0.5}

EXEMPLO 4 — venda: colete o essencial e passe pro comercial
Cliente: "vocês vendem impressora de etiqueta?"
Você: {"resposta_cliente": "Vendemos sim! Trabalhamos com impressoras de etiqueta e
todo o resto da automação. Me diz o nome da sua empresa e qual o uso que você
pretende dar (gôndola, balança, produto), que já passo para o nosso consultor com
tudo em mãos.", "acao": "responder", "setor": "NENHUM", "criar_lead": "",
"confianca": 0.8}

EXEMPLO 5 — cliente irritado: acolha e passe adiante rápido
Cliente: "isso não funciona nunca, quero falar com alguém AGORA"
Você: {"resposta_cliente": "Entendo perfeitamente, e sinto muito pelo transtorno.
Vou te passar agora mesmo para um técnico da equipe cuidar disso com você.",
"acao": "transferir", "setor": "SUPORTE", "criar_lead": "", "confianca": 0.9}
"""


def montar_prompt(is_plantao, base_conhecimento, historico, texto_cliente,
                  sistema_cliente="Não identificado", aviso_audio="", trava_loop=""):
    """
    Monta o prompt da IA. UM prompt só para os dois cenários — o que muda entre
    dia e plantão vira parâmetro, não um segundo texto duplicado.

    Antes existiam dois prompts gigantes quase idênticos: toda regra precisava
    ser editada em dois lugares e uma hora eles divergiam. Agora a identidade da
    empresa e as regras de negócio vêm do BotConfig (editáveis no admin).
    """
    config = BotConfig.objects.first()

    identidade = (getattr(config, "identidade_empresa", "") or "").strip() or IDENTIDADE_PADRAO
    regras = (getattr(config, "regras_negocio", "") or "").strip() or REGRAS_PADRAO

    # NOTA: o campo BotConfig.instrucoes_suporte_24h NÃO é mais lido aqui.
    # A fonte de conhecimento técnico passou a ser exclusivamente a WIKI, via
    # busca semântica — assim a IA recebe só o trecho relevante para cada dúvida,
    # em vez do manual inteiro em toda mensagem.
    # O conteúdo antigo continua salvo no campo, como referência/backup.
    # Para voltar a usá-lo, basta reinserir a seção [MANUAL INTERNO] no prompt.

    if is_plantao:
        persona = (getattr(config, "prompt_analista_digital", "") or "").strip() or (
            "Você é Lia, Analista Digital de Plantão da Lógica Tecnologia. "
            "A equipe humana encerrou o expediente, mas você está aqui."
        )
        contexto_tempo = (
            "É FORA DO HORÁRIO COMERCIAL. Não há técnico humano disponível agora — a equipe "
            "retorna no próximo dia útil. Quando transferir, explique que o caso fica "
            "registrado para a equipe atender amanhã cedo."
        )
        nota_risco = (
            "À noite não há técnico pra corrigir um erro seu — então prefira registrar para "
            "amanhã a arriscar um passo que pode piorar a situação do cliente."
        )
    else:
        persona = (getattr(config, "prompt_ia_triagem", "") or "").strip() or (
            "Você é Lia, Analista Digital da Lógica Tecnologia e Automação Comercial."
        )
        contexto_tempo = (
            "É HORÁRIO COMERCIAL. Há técnicos humanos disponíveis agora. Quando transferir, "
            "o cliente será atendido em seguida por uma pessoa da equipe."
        )
        nota_risco = (
            "Prefira dizer 'vou chamar um especialista' a arriscar um passo errado."
        )

    return f"""
{persona}

[COMO VOCÊ ESCREVE]
Somos uma empresa parceira do cliente — trate com respeito e empatia, num tom de
quem está do lado dele resolvendo junto. Nada de formalidade fria nem de
informalidade forçada.
- Vá direto ao ponto. Evite rodeios e frases de enfeite.
- Numa conversa normal (saudação, pergunta, aviso), 1 a 3 linhas bastam.
- Ao ensinar um procedimento, use quantas linhas precisar: numere os passos
  (1, 2, 3), um por linha. É melhor ser completa do que curta.
- NUNCA envie frase cortada ou pela metade.
- Nunca diga "segundo o documento", "não consta na minha base" ou similar. O
  cliente não precisa saber como você consulta as informações.

[CONTEXTO DE ATENDIMENTO]
{contexto_tempo}

[QUEM SOMOS NÓS - IDENTIDADE DA EMPRESA]
{identidade}

[CONTEXTO DO CLIENTE]
Sistema(s) que este cliente utiliza: {sistema_cliente}

[BASE TÉCNICA - ARTIGOS ENCONTRADOS PARA ESTE CASO]
{base_conhecimento if base_conhecimento else "(Nenhum artigo específico encontrado para esta dúvida.)"}

[REGRAS DE NEGÓCIO DA EMPRESA]
{regras}

[DIRETRIZES DE ATENDIMENTO - O SEU CÉREBRO]
Analise o histórico e a mensagem atual para decidir como agir:

ETAPA 1: O cliente só cumprimentou ("oi", "bom dia") sem trazer assunto?
- Se a conversa está começando: cumprimente de volta e pergunte como pode ajudar.
- Se JÁ existe um assunto em andamento no histórico: retome de onde parou, não
  volte à estaca zero. (Ex: se ele já disse que usa Raffinato e mandou "oi", não
  pergunte tudo de novo.)
- Não transfira só por causa de um cumprimento.

ETAPA 2: FINANCEIRO — siga as [REGRAS DE NEGÓCIO] acima.

ETAPA 3: O cliente quer COMPRAR (sistemas, equipamentos, bobinas)?
- NÓS VENDEMOS SIM! Faça perguntas curtas para descobrir: 1) nome da empresa,
  2) o que ele precisa comprar.
- Quando já souber, use acao=transferir com setor=COMERCIAL.
- OBRIGATÓRIO: preencha criar_lead com "Empresa | Nome do contato | Dor principal".

ETAPA 4: O cliente relatou um PROBLEMA TÉCNICO ou DÚVIDA?
- PRIMEIRO INVESTIGUE: se o relato for vago ("não funciona", "deu erro", "não entra"),
  faça UMA pergunta curta pra entender (qual mensagem aparece? em qual tela? desde
  quando?). Uma pergunta por vez — nunca um interrogatório.
- NÃO REPITA PERGUNTA JÁ RESPONDIDA: se o sistema (Clipp, Raffinato...) ou qualquer
  outro dado já aparece no histórico, use a informação e siga em frente.
- DEPOIS RESOLVA JUNTO: se a [BASE TÉCNICA] cobre o caso,
  conduza o cliente pelo passo a passo, com calma, quantas mensagens forem
  necessárias até resolver. Pergunte se deu certo antes de encerrar.
- NUNCA invente procedimento que não esteja na [BASE TÉCNICA].
- SÓ TRANSFIRA se: já investigou e não há solução documentada, OU o caso exige
  acesso ao servidor/sistema do cliente. Use acao=transferir e setor=SUPORTE.

ETAPA 5: EMERGÊNCIA
- Cliente muito irritado, sistema 100% parado, ou pedido explícito de falar com
  humano: acolha em uma frase e use acao=transferir com setor=SUPORTE.
  Não insista em resolver sozinha quando pedem uma pessoa.

ETAPA 6: VISÃO RAIO-X (IMAGENS)
- Se o texto começar com "📷 Imagem", olhe atentamente a foto anexada e cruze o erro
  com a [BASE TÉCNICA]. Se a solução estiver lá, conduza o
  passo a passo.
- NUNCA peça para o cliente descrever o que está na imagem — você consegue vê-la.
- Se não souber resolver o que viu, diga que leu o erro e encaminhe pra equipe,
  com acao=transferir e setor=SUPORTE.

[LIMITES - O QUE VOCÊ NUNCA FAZ]
- NUNCA informe preço, valor, desconto ou condição de pagamento. Isso é do
  Comercial. Diga que o consultor passa os valores.
- NUNCA prometa prazo de atendimento, de visita ou de entrega ("amanhã cedo",
  "em 2 horas"). Você não controla a agenda da equipe.
- NUNCA garanta que algo será resolvido, corrigido ou desenvolvido.
- NUNCA fale mal de concorrente, nem comente assunto pessoal, político ou fora
  do escopo da Lógica — redirecione com gentileza.
- Na dúvida entre prometer e não prometer: não prometa.

[EXEMPLOS DE COMO VOCÊ RESPONDE]
{EXEMPLOS_PADRAO}

[COMO VOCÊ DEVE RESPONDER - FORMATO OBRIGATÓRIO]
Responda SEMPRE no formato JSON estruturado, com estes campos:
- resposta_cliente: o texto que o cliente vai ler no WhatsApp. Natural, humano e SEM
  colchetes/tags. Nunca escreva [SUPORTE] ou similar aqui.
- acao: "responder", "transferir", "encerrar" ou "silencio".
- setor: só quando acao=transferir. SUPORTE, ASSISTENCIA, COMERCIAL ou FINANCEIRO.
- criar_lead: só em caso de venda (ETAPA 3). Caso contrário, vazio.
- confianca: SEJA HONESTA. Sua certeza REAL de que a resposta resolve o caso:
    * 0.9-1.0 = a [BASE TÉCNICA] tem exatamente este caso.
    * 0.6-0.8 = você sabe responder com segurança (saudação, dúvida simples, ou uma
      pergunta investigativa que você mesma está fazendo).
    * ABAIXO DE 0.6 = você NÃO tem a informação. NÃO invente procedimento: ou pergunte
      mais, ou transfira.
  {nota_risco}

[HISTÓRICO RECENTE DA CONVERSA]
{historico}
{trava_loop}

[NOVA MENSAGEM DO CLIENTE]
Cliente: "{texto_cliente}"
{aviso_audio}

Responda agora no formato JSON estruturado descrito acima.
"""


def interpretar_resposta_ia(dados, session, contexto="TRIAGEM"):
    """
    Normaliza o JSON da IA e aplica as REGRAS DE SEGURANÇA de confiança.

    Devolve (texto, acao_final, setor) onde acao_final ∈
    {"responder","transferir","encerrar","silencio"}.

    A regra de ouro: confiança baixa NUNCA vira afirmação técnica. Se a IA
    está insegura e já vem tentando há algumas rodadas, mandamos pro humano
    em vez de deixá-la inventar.
    """
    texto = (dados.get("resposta_cliente") or "").strip()
    acao = (dados.get("acao") or "responder").strip().lower()
    setor = (dados.get("setor") or "").strip().upper()
    try:
        confianca = float(dados.get("confianca", 0.5))
    except (TypeError, ValueError):
        confianca = 0.5

    if setor in ("NENHUM", ""):
        setor = None

    logger.info(
        f"🧠 [IA {contexto}] acao={acao} | setor={setor} | confianca={confianca:.2f} "
        f"| sessao={session.id}"
    )

    # ── Rede de segurança: insegura + já tentou antes = manda pro humano ──
    if acao == "responder" and confianca < LIMIAR_CONFIANCA:
        tentativas = Message.objects.filter(session=session, sender_type='IA').count()
        if tentativas >= 2:
            logger.warning(
                f"⚠️ [CONFIANÇA BAIXA] {confianca:.2f} após {tentativas} tentativas. "
                f"Transferindo em vez de arriscar. Sessão: {session.id}"
            )
            Message.objects.create(
                session=session, sender_type='SISTEMA',
                text=f"🛡️ IA transferiu por baixa confiança ({confianca:.0%})"
            )
            return (
                "Pra não te passar informação errada, vou chamar um especialista da "
                "nossa equipe pra olhar isso com você, tudo bem?",
                "transferir",
                setor or "SUPORTE",
            )

    if acao == "transferir" and not setor:
        setor = "SUPORTE"

    return texto, acao, setor
def gerar_audio_gemini(api_key, texto_para_falar):
    print(f"\n[LOG TRILHA IA] 1. Iniciando TTS para o texto: '{texto_para_falar[:50]}...'", flush=True)

    # Modelo e voz agora vêm do BotConfig (configuráveis no admin, sem mexer em
    # código). Padrões = o que já estava em uso, então nada muda até você trocar.
    modelo_tts = "gemini-2.5-flash-preview-tts"
    voz_tts = "Vindemiatrix"
    try:
        config = BotConfig.objects.first()
        if config:
            modelo_tts = (getattr(config, "modelo_tts", "") or "").strip() or modelo_tts
            voz_tts = (getattr(config, "voz_tts", "") or "").strip() or voz_tts
    except Exception as e:
        print(f"[TTS] Falha ao ler config de voz, usando padrão: {e}", flush=True)

    url = f"https://generativelanguage.googleapis.com/v1alpha/models/{modelo_tts}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": texto_para_falar}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz_tts}}}
        }
    }
    try:
        res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=60)
        if res.status_code == 200:
            print("[LOG TRILHA IA] 2. Google respondeu com Sucesso (200).", flush=True)
            partes = res.json().get('candidates', [{}])[0].get('content', {}).get('parts', [])
            for p in partes:
                if 'inlineData' in p: 
                    print("[LOG TRILHA IA] 3. Áudio gerado! Formatando Base64...", flush=True)
                    data = p['inlineData']['data']
                    data = data.replace('-', '+').replace('_', '/')
                    data += "=" * ((4 - len(data) % 4) % 4)
                    return data
            print("[ERRO TRILHA IA] Google deu 200, mas NÃO enviou o áudio!", flush=True)
        else: 
            print(f"\n[ERRO GEMINI TTS] Status: {res.status_code} | {res.text}\n", flush=True)
    except Exception as e:
        print(f"\n[ERRO CONEXAO TTS] Falha na rede: {e}\n", flush=True)
    return None
    
def processar_triagem_ia(session, texto_cliente, media_url=None, base64_media=None, mime_type=None):
    import logging
    logger = logging.getLogger('rastreador_zap')
    
    logger.info(f"⚡ [CHEGOU MSG] Sessao: {session.id} | Tem Mídia? {mime_type} | Texto: {texto_cliente[:30]}")
    
    config = BotConfig.objects.first()
    if not config or not config.chave_api_gemini: 
        logger.warning(f"⚠️ [FALHA] Sem config ou sem chave API. Sessão: {session.id}")
        return {"acao": "MENU"}
        
    ultima_msg = Message.objects.filter(session=session).exclude(sender_type='SISTEMA').order_by('-timestamp').first()
    if ultima_msg and ultima_msg.sender_type != 'CLIENTE': 
        logger.info(f"🛑 [TRAVA LOOP] Última mensagem não foi do cliente (foi {ultima_msg.sender_type}). Abortando para evitar loop. Sessão: {session.id}")
        return {"acao": "MENSAGEM", "texto": None}

    cliente_mandou_audio = False
    aviso_audio = ""
    if mime_type and 'audio' in mime_type:
        cliente_mandou_audio = True
        aviso_audio = "\n[ATENÇÃO: O cliente enviou um ÁUDIO. Sua resposta será lida por uma voz sintética. Escreva de forma CONVERSACIONAL, ACOLHEDORA e COM EMPATIA, como um humano falando, mas MANTENHA A MENSAGEM CURTA. Use pontuação expressiva (!, ?) para dar entonação e 'sorriso na voz'.]\n"
        logger.info(f"🎵 [ÁUDIO DETECTADO] Cliente mandou áudio. Preparando prompt conversacional. Sessão: {session.id}")
        
    texto_lower = str(texto_cliente).lower().strip()
    gatilhos = ["pode finalizar", "pode encerrar", "já resolvi", "ja resolvi", "não precisa mais", "nao precisa mais", "encerrar atendimento", "finalizar atendimento"]
    for g in gatilhos:
        if g in texto_lower:
            session.status = 'FINALIZADO'; session.save()
            logger.info(f"🔒 [GATILHO ENCERRAR] Cliente digitou '{g}'. Sessão {session.id} finalizada.")
            return {"acao": "MENSAGEM", "texto": "Maravilha! Qualquer coisa é só chamar. Um abraço! 👋", "audio_b64": None}
    
    chave_limpa = config.chave_api_gemini.strip()

    # 🔥 NOVO CÉREBRO INVESTIGATIVO: Descobrindo o sistema do cliente antes de agir
    sistema_cliente = "Não identificado"
    if session.cliente:
        sistemas = []
        if hasattr(session.cliente, 'sistemas_vinculados') and session.cliente.sistemas_vinculados.all():
            sistemas = [str(s) for s in session.cliente.sistemas_vinculados.all()]
        elif hasattr(session.cliente, 'sistemas') and session.cliente.sistemas.all():
            sistemas = [str(s) for s in session.cliente.sistemas.all()]
        elif hasattr(session.cliente, 'sistema_atual') and getattr(session.cliente, 'sistema_atual', None):
            sistemas = [str(session.cliente.sistema_atual)]
        elif hasattr(session.cliente, 'sistema') and getattr(session.cliente, 'sistema', None):
            sistemas = [str(session.cliente.sistema)]
        if sistemas:
            sistema_cliente = " / ".join(sistemas)

    if session.status == 'TRIAGEM' and a_empresa_esta_aberta():
        # Conectando o Hipocampo (Memória)
        from .ia_memoria import obter_historico

        historico = obter_historico(session, limite=12)

        # 🔎 BUSCA SEMÂNTICA NOVA (significado + filtro por sistema do cliente + Geral).
        # Substitui a antiga busca por palavra-chave. Passa o cliente da sessão
        # pra filtrar pelos sistemas dele. Nunca derruba o fluxo: na falha, o
        # contexto vem vazio e a IA segue (como já fazia antes).
        base_conhecimento = None
        try:
            from base_conhecimento.busca import buscar, formatar_para_ia
            resultado_busca = buscar(texto_cliente, cliente=session.cliente, api_key=chave_limpa)
            base_conhecimento = formatar_para_ia(resultado_busca)
        except Exception as e:
            logger.error(f"[BUSCA RAG] Falha na busca semântica (seguindo sem base): {e}")
            base_conhecimento = None
        
        qtd_respostas_ia = historico.count("Você (IA):")
        # Dá mais margem para a IA investigar antes de cortar
        trava_loop = "\n[CONTEXTO INTERNO]: O cliente já conversou com você algumas vezes. Se a situação já estiver clara e não houver como resolver, use acao=transferir com o setor correto." if qtd_respostas_ia >= 4 else ""

        prompt = montar_prompt(
            is_plantao=False,
            base_conhecimento=base_conhecimento,
            historico=historico,
            texto_cliente=texto_cliente,
            sistema_cliente=sistema_cliente,
            aviso_audio=aviso_audio,
            trava_loop=trava_loop,
        )

        print(f"\n[LOG TRILHA IA] Chamando IA (JSON)... Cliente enviou áudio? {cliente_mandou_audio}", flush=True)
        logger.info(f"🤖 [GEMINI CALL] Chamando IA estruturada (Triagem). Sessão: {session.id}")
        dados_ia = chamar_gemini_json(chave_limpa, prompt, base64_media, mime_type)

        if not dados_ia:
            logger.error(f"❌ [FALHA GEMINI] IA não retornou JSON válido na Triagem. Sessão: {session.id}")
            return {"acao": "TRANSFERIR", "setor": "SUPORTE",
                    "texto_ia": "Tive uma falha de conexão na minha IA, mas já estou transferindo seu atendimento para a nossa equipe técnica!",
                    "audio_b64": None}

        # 🦾 CÓRTEX MOTOR (CRM): agora o lead vem em campo próprio, sem regex
        dados_lead = (dados_ia.get("criar_lead") or "").strip()
        if dados_lead:
            try:
                from .ia_ferramentas import processar_comando_lead
                processar_comando_lead(dados_lead, session.whatsapp_number)
                logger.info(f"💼 [LEAD] Lead criado pela IA: {dados_lead[:60]}")
            except Exception as e:
                logger.error(f"[ERRO MOTOR CRM] Erro ao chamar ia_ferramentas: {e}")

        # Interpreta e aplica a regra de confiança
        texto_ia, acao_ia, setor_ia = interpretar_resposta_ia(dados_ia, session, contexto="TRIAGEM")

        if acao_ia == "silencio":
            logger.info(f"🤫 [SILENCIO] IA decidiu não responder. Sessão: {session.id}")
            return {"acao": "MENSAGEM", "texto": None, "audio_b64": None}

        # Áudio (se o cliente mandou áudio, respondemos por voz)
        audio_ia = None
        texto_whatsapp = texto_ia
        if texto_ia and cliente_mandou_audio:
            texto_para_voz = texto_ia.strip()
            if len(texto_para_voz) < 5:
                texto_para_voz = "Tudo certo, já anotei aqui e vou repassar para a nossa equipe. Um instante."
            logger.info(f"🎤 [GEMINI TTS] Chamando TTS (Triagem). Texto: {texto_para_voz[:30]}...")
            audio_ia = gerar_audio_gemini(chave_limpa, texto_para_voz)
            if audio_ia:
                texto_whatsapp = "🎙️ Ouça o áudio abaixo com o retorno do seu atendimento:"

        txt = (texto_whatsapp or "").strip().replace('*', '').replace('#', '')

        if acao_ia == "encerrar":
            session.status = 'FINALIZADO'; session.save()
            logger.info(f"🏁 [ENCERRAR] IA finalizou o atendimento. Sessão: {session.id}")
            return {"acao": "MENSAGEM", "texto": txt or "Show! Qualquer coisa é só chamar. 👋", "audio_b64": audio_ia}

        if acao_ia == "transferir":
            if not audio_ia and (not txt or len(txt) < 10):
                txt = "Tudo certo! Já anotei tudo e estou transferindo para a nossa equipe. Um instante!"
            Message.objects.create(session=session, sender_type='SISTEMA',
                                   text=f"📌 TRIAGEM DA IA: Cliente direcionado para {setor_ia}")
            logger.info(f"🔀 [ROTEAMENTO] IA decidiu transferir. Setor: {setor_ia}. Sessão: {session.id}")
            return {"acao": "TRANSFERIR", "setor": setor_ia, "texto_ia": txt, "audio_b64": audio_ia}

        # Trava de loop: cliente preso conversando com a IA sem sair do lugar
        if qtd_respostas_ia >= 6:
            msg_trava = "Entendi. Vou repassar o seu caso para um de nossos especialistas analisar agora mesmo. Só um momento."
            audio_trava = gerar_audio_gemini(chave_limpa, msg_trava) if cliente_mandou_audio else None
            texto_trava_whatsapp = "🎙️ Ouça o áudio abaixo com o retorno da transferência:" if audio_trava else msg_trava
            logger.warning(f"🛑 [TRAVA LOOP] Cliente preso na triagem (respostas: {qtd_respostas_ia}). Forçando transferência. Sessão: {session.id}")
            return {"acao": "TRANSFERIR", "setor": "SUPORTE", "texto_ia": texto_trava_whatsapp, "audio_b64": audio_trava}

        logger.info(f"💬 [CONVERSA] IA manteve a conversa na triagem. Sessão: {session.id}")
        return {"acao": "MENSAGEM", "texto": txt, "audio_b64": audio_ia}

    # BLOCO 2: EMPRESA FECHADA (CÉREBRO HUMANO DO PLANTÃO)
    if not a_empresa_esta_aberta():
        if session.status == 'TRIAGEM':
            session.status = 'SUPORTE_IA'; session.save()
            logger.info(f"🌙 [FORA HORÁRIO] Mudando sessão de Triagem para Suporte IA. Sessão: {session.id}")
            return {"acao": "MENSAGEM", "texto": config.mensagem_fora_horario}
        
        msgs_plantao = list(Message.objects.filter(session=session).order_by('-timestamp')[:15])
        historico_plantao = "\n".join([f"{'Você (IA)' if m.sender_type == 'IA' else 'Cliente'}: {m.text}" for m in reversed(msgs_plantao)])

        # 🌙 Conhecimento técnico vem da WIKI (busca semântica), igual ao diurno.
        base_conhecimento = None
        try:
            from base_conhecimento.busca import buscar, formatar_para_ia
            resultado_busca = buscar(texto_cliente, cliente=session.cliente, api_key=chave_limpa)
            base_conhecimento = formatar_para_ia(resultado_busca)
        except Exception as e:
            logger.error(f"[BUSCA RAG PLANTÃO] Falha na busca semântica (seguindo sem wiki): {e}")
            base_conhecimento = None

        prompt_plantao = montar_prompt(
            is_plantao=True,
            base_conhecimento=base_conhecimento,
            historico=historico_plantao,
            texto_cliente=texto_cliente,
            sistema_cliente=sistema_cliente,
            aviso_audio=aviso_audio,
        )
        logger.info(f"🤖 [GEMINI CALL] Chamando IA estruturada (Plantão). Sessão: {session.id}")
        dados_ia = chamar_gemini_json(chave_limpa, prompt_plantao, base64_media, mime_type)

        if not dados_ia:
            logger.error(f"❌ [FALHA GEMINI] IA não retornou JSON válido no Plantão. Sessão: {session.id}")
            return {"acao": "MENSAGEM",
                    "texto": "Tivemos uma falha de conexão com a nossa IA. Por favor, tente enviar sua mensagem novamente em alguns instantes.",
                    "audio_b64": None}

        # 🦾 CÓRTEX MOTOR (CRM - NOITE): lead em campo próprio
        dados_lead = (dados_ia.get("criar_lead") or "").strip()
        if dados_lead:
            try:
                from .ia_ferramentas import processar_comando_lead
                processar_comando_lead(dados_lead, session.whatsapp_number)
                logger.info(f"💼 [LEAD PLANTÃO] Lead criado pela IA: {dados_lead[:60]}")
            except Exception as e:
                logger.error(f"[ERRO MOTOR CRM] Erro ao chamar ia_ferramentas no plantão: {e}")

        texto_ia, acao_ia, setor_ia = interpretar_resposta_ia(dados_ia, session, contexto="PLANTÃO")

        if acao_ia == "silencio":
            logger.info(f"🤫 [SILENCIO PLANTAO] IA decidiu ignorar. Sessão: {session.id}")
            return {"acao": "MENSAGEM", "texto": None, "audio_b64": None}

        audio_ia = None
        texto_whatsapp = texto_ia
        if texto_ia and cliente_mandou_audio:
            logger.info(f"🎤 [GEMINI TTS] Chamando TTS (Plantão). Texto: {texto_ia[:30]}...")
            audio_ia = gerar_audio_gemini(chave_limpa, texto_ia.strip())
            if audio_ia:
                texto_whatsapp = "🎙️ Ouça o áudio abaixo com o retorno do plantão:"

        txt = (texto_whatsapp or "").strip()

        if acao_ia == "encerrar":
            session.status = 'FINALIZADO'; session.save()
            msg_final = txt or "Show! Atendimento encerrado. Qualquer coisa dá um grito amanhã. Bom descanso! 👋"
            if audio_ia:
                msg_final = "🎙️ Atendimento encerrado. Detalhes no áudio:"
            logger.info(f"🏁 [ENCERRAR PLANTAO] IA decidiu encerrar conversa no Plantão. Sessão: {session.id}")
            return {"acao": "MENSAGEM", "texto": msg_final, "audio_b64": audio_ia}

        if acao_ia == "transferir":
            if not audio_ia and (not txt or len(txt) < 5):
                txt = "Tudo certo! Já anotei tudo e deixei na mesa da nossa equipe para amanhã."
            Message.objects.create(session=session, sender_type='SISTEMA',
                                   text=f"📌 PLANTÃO IA DIRECIONOU PARA: {setor_ia}")
            logger.info(f"🔀 [ROTEAMENTO PLANTÃO] Setor: {setor_ia}. Sessão: {session.id}")
            return {"acao": "TRANSFERIR", "setor": setor_ia, "texto_ia": txt, "audio_b64": audio_ia}

        logger.info(f"💬 [CONVERSA PLANTAO] Resposta normal. Sessão: {session.id}")
        return {"acao": "MENSAGEM", "texto": txt, "audio_b64": audio_ia}

    logger.warning(f"❓ [FALLBACK] Cedeu Fallback! O sistema não soube o que fazer. Sessão: {session.id}")
    return {"acao": "FALLBACK"}

def processar_notas_cs(session, texto):
    numero = re.sub(r'\D', '', texto)
    if not numero: return False
    valor = int(numero)
    if session.status == 'AVALIACAO_TECNICO' and 1 <= valor <= 5:
        session.nota_tecnico = valor; session.status = 'AVALIACAO_NPS'; session.save(); return True
    if session.status == 'AVALIACAO_NPS' and 0 <= valor <= 10:
        session.nota_nps = valor; session.status = 'FINALIZADO'; session.save(); return True
    return False

def transcrever_audio_gemini(api_key, base64_media, mime_type):
    """
    Córtex Auditivo: Escuta o áudio do cliente e devolve apenas o texto falado.
    """
    modelo = "models/gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    prompt = "Transcreva este áudio com máxima exatidão. Responda APENAS com a transcrição, sem aspas, sem adicionar nenhum comentário. Se o áudio for só ruído ou mudo, retorne exatamente: [Áudio sem voz]"
    
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime_type, "data": base64_media}}
        ]}],
        "generationConfig": {"temperature": 0.1}
    }
    
    try:
        import requests
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            texto = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return texto if "[Áudio sem voz]" not in texto else None
    except Exception as e:
        import logging
        logging.getLogger('rastreador_zap').error(f"[ERRO TRANSCRICAO] {e}")
    return None