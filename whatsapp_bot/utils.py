import openai
from django.utils import timezone
from base_conhecimento.models import Artigo # Ajuste o nome do seu app de base
from .models import Message

def buscar_na_base_conhecimento(pergunta):
    """
    Busca simples por texto nos artigos da base de conhecimento.
    No futuro, podemos usar busca vetorial para ser mais preciso.
    """
    artigos = Artigo.objects.filter(ativo=True)
    contexto = ""
    
    # Filtra artigos que tenham palavras-chave da pergunta
    palavras = pergunta.lower().split()
    for artigo in artigos:
        if any(p in artigo.titulo.lower() or p in artigo.conteudo.lower() for p in palavras):
            contexto += f"\n--- Artigo: {artigo.titulo} ---\n{artigo.conteudo}\n"
    
    return contexto[:3000] # Limita o tamanho do contexto para a IA

def responder_com_ia(pergunta, session):
    """
    Consulta a OpenAI/Gemini usando a base de conhecimento como contexto.
    """
    agora = timezone.localtime()
    # Define horário de expediente: Seg-Sex, 07:20 às 18:00
    is_expediente = (0 <= agora.weekday() <= 4) and (time(7, 20) <= agora.time() <= time(18, 0))
    
    contexto_base = buscar_na_base_conhecimento(pergunta)
    
    prompt = f"""
    Você é o Assistente Inteligente do Union Desk (Lógica Automação).
    Seu objetivo é auxiliar técnicos e clientes com base no CONTEXTO abaixo.
    
    CONTEXTO DA EMPRESA:
    {contexto_base}
    
    DIRETRIZES:
    1. Se for fora do expediente e você não souber a resposta, peça para o cliente aguardar o plantão.
    2. Se for horário de expediente, tente resolver, mas se for complexo, diga que um técnico assumirá em breve.
    3. Nunca invente funcionalidades que não estão no contexto.
    4. O cliente atual é da empresa: {session.cliente.razao_social if session.cliente else 'Desconhecida'}.
    """

    # Aqui você chamaria a API da sua escolha (OpenAI/Gemini)
    # Exemplo com estrutura OpenAI:
    # response = openai.ChatCompletion.create(model="gpt-4", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": pergunta}])
    # return response.choices[0].message.content

    return "IA PROCESSANDO: (Aqui retornaria a resposta baseada na sua base de conhecimento)"