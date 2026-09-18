# /whatsapp_bot/ia_memoria.py
import re
from django.db.models import Q
from django.utils.html import strip_tags
from base_conhecimento.models import Artigo
from .models import Message

def extrair_palavras_chave(texto):
    # Removemos palavras comuns para a busca ficar cirúrgica (estilo Google)
    stopwords = [
        'o', 'a', 'os', 'as', 'um', 'uma', 'de', 'do', 'da', 'em', 'no', 'na', 
        'por', 'para', 'com', 'como', 'que', 'eu', 'você', 'ele', 'me', 'te', 
        'meu', 'minha', 'seu', 'sua', 'este', 'esse', 'isso', 'está', 'é', 'são', 
        'fazer', 'quero', 'preciso', 'gostaria', 'sistema', 'ajuda', 'erro', 'problema',
        'boa', 'tarde', 'dia', 'noite', 'olá', 'ola', 'oi'
    ]
    # Pega só palavras com 3 letras ou mais
    palavras = re.findall(r'\b\w{3,}\b', str(texto).lower())
    return [p for p in palavras if p not in stopwords]

def buscar_artigos_relevantes(mensagem_cliente, limite=2):
    palavras_chave = extrair_palavras_chave(mensagem_cliente)
    
    if not palavras_chave:
        return None

    # Constrói a busca (OR) para Título, Conteúdo ou Hashtags
    query = Q()
    for palavra in palavras_chave:
        query |= Q(titulo__icontains=palavra) | Q(conteudo__icontains=palavra) | Q(hashtags__icontains=palavra)

    # Busca no banco (distinto para não repetir o mesmo artigo)
    artigos = Artigo.objects.filter(query).distinct()[:limite]
    
    if not artigos.exists():
        return None

    # Formata o texto mastigado para a IA ler
    contexto = "📚 BASE DE CONHECIMENTO ENCONTRADA (Use isso para ajudar o cliente se aplicável):\n\n"
    for art in artigos:
        # strip_tags remove o HTML do RichText, deixando só o texto puro!
        conteudo_limpo = strip_tags(art.conteudo).strip()
        # Limita a 1500 caracteres por artigo para não explodir a memória
        conteudo_limpo = conteudo_limpo[:1500] + "..." if len(conteudo_limpo) > 1500 else conteudo_limpo
        
        contexto += f"🔹 TÍTULO: {art.titulo} (Cód: {art.codigo})\n"
        contexto += f"📝 CONTEÚDO: {conteudo_limpo}\n\n"
        
    return contexto

def obter_historico(session, limite=12):
    msgs = list(Message.objects.filter(session=session).exclude(sender_type='SISTEMA').order_by('-timestamp')[:limite])
    historico = "\n".join([f"{'Você (IA)' if m.sender_type == 'IA' else 'Cliente'}: {m.text}" for m in reversed(msgs)])
    return historico