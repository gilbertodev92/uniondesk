import base64
import json
import logging

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from whatsapp_bot.bot_engine import chamar_gemini_rest
from whatsapp_bot.models import BotConfig, ChatSession
from whatsapp_bot.ia_memoria import obter_historico

from .models import UsoAssistenteIA

logger = logging.getLogger("rastreador_zap")

# Curto, direto, sem enrolação — no tom que o analista realmente usa no dia a
# dia (mensagem rápida pra um colega), não um atendimento formal ao cliente.
PROMPT_SISTEMA = """Você é o assistente interno do UnionDESK. Está respondendo
direto pra um analista/técnico da equipe, não pro cliente final — é como se
fosse o gerente/mais experiente da equipe orientando na hora.

Como responder:
- Direto ao ponto, sem preâmbulo, sem repetir o que a pessoa disse, sem frases
  de preenchimento tipo "que chato", "vamos com calma", "fico feliz em ajudar".
- Curto. Poucas frases. Só alongue se for passo a passo técnico que realmente
  precisa de várias etapas — e mesmo assim, direto, numerado se ajudar.
- Tom de colega mandando mensagem rápida, igual o analista fala com você:
  informal, sem formalidade de atendimento.
- RESOLVA, não empurre. Se a base de conhecimento (wiki) trouxer o
  procedimento, dê o passo a passo real ali mesmo — não diga só "manda pro
  Suporte" ou "abre chamado" quando você já tem a informação de como fazer.
  Escalar/transferir só faz sentido quando o problema exige algo que o
  analista genuinamente não tem acesso pra fazer sozinho (servidor, instalação
  remota, etc.) — não como saída fácil.
- Só admita que não sabe quando a base de conhecimento realmente não trouxe
  nada sobre o assunto. Nesse caso sim, diga em uma frase e sugira o próximo
  passo (perguntar tal coisa específica pro cliente, escalar pra quem tem
  acesso, etc.) — mas isso é exceção, não o padrão.
- Se vier uma imagem (print de erro, tela do sistema), analise ela direto e
  responda com base no que aparece nela."""


@login_required
@require_POST
@csrf_protect
def assistente_perguntar(request):
    try:
        dados = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"erro": "Corpo da requisição inválido."}, status=400)

    pergunta = (dados.get("pergunta") or "").strip()
    pagina = (dados.get("pagina") or "")[:255]
    session_id = dados.get("session_id")  # opcional: se o analista está numa conversa do whatsapp_bot
    contexto_extra = (dados.get("contexto") or "").strip()  # opcional: texto que a própria tela já monta
    imagem_base64 = dados.get("imagem_base64")  # opcional: print colado/anexado pelo analista
    imagem_mime = dados.get("imagem_mime")

    if not pergunta and not imagem_base64:
        return JsonResponse({"erro": "Pergunta vazia."}, status=400)
    pergunta = pergunta or "Analise essa imagem e me ajuda com isso."

    config = BotConfig.objects.first()
    if not config or not config.chave_api_gemini:
        return JsonResponse({"erro": "IA não configurada (BotConfig sem chave)."}, status=500)

    chave = config.chave_api_gemini.strip()
    partes_prompt = [PROMPT_SISTEMA]

    if config.identidade_empresa:
        partes_prompt.append(f"[QUEM SOMOS]\n{config.identidade_empresa}")
    if config.regras_negocio:
        partes_prompt.append(f"[REGRAS DE NEGÓCIO]\n{config.regras_negocio}")

    # se o analista está dentro de um atendimento do whatsapp_bot, traz o
    # histórico da conversa pro assistente já saber do que se trata
    session = None
    if session_id:
        session = ChatSession.objects.filter(pk=session_id).first()
        if session:
            historico = obter_historico(session, limite=12)
            if historico:
                partes_prompt.append(f"[HISTÓRICO DA CONVERSA ATUAL]\n{historico}")

    # busca semântica na wiki (base_conhecimento) usando a pergunta do analista
    # limite/max_chars maiores que o padrão do bot de cliente: aqui é o
    # analista lendo, então vale trazer mais contexto pra IA poder dar o
    # passo a passo completo em vez de só a pontinha do artigo
    try:
        from base_conhecimento.busca import buscar, formatar_para_ia
        resultado_busca = buscar(
            pergunta,
            cliente=session.cliente if session else None,
            limite=6,
            api_key=chave,
        )
        base_kb = formatar_para_ia(resultado_busca, max_chars_por_artigo=2500)
        if base_kb:
            partes_prompt.append(base_kb)
    except Exception as e:
        logger.error(f"[ASSISTENTE FLUTUANTE] Falha na busca da wiki (seguindo sem ela): {e}")

    if contexto_extra:
        partes_prompt.append(f"[CONTEXTO DA TELA ATUAL]\n{contexto_extra}")

    nome_analista = request.user.first_name or request.user.username
    partes_prompt.append(f"[PERGUNTA DE {nome_analista.upper()}]\n{pergunta}")

    prompt_final = "\n\n".join(partes_prompt)

    # a imagem pode chegar como data URI ("data:image/png;base64,...."); o
    # chamar_gemini_rest espera só o base64 puro
    base64_limpo = None
    if imagem_base64:
        base64_limpo = imagem_base64.split(",", 1)[-1] if "," in imagem_base64 else imagem_base64

    resposta = chamar_gemini_rest(
        chave, prompt_final,
        base64_media=base64_limpo,
        mime_type=imagem_mime if base64_limpo else None,
    )
    if not resposta:
        return JsonResponse({"erro": "Falha ao consultar a IA. Tente novamente."}, status=502)

    resposta = resposta.strip()

    UsoAssistenteIA.objects.create(
        analista=request.user,
        pergunta=pergunta,
        resposta=resposta,
        pagina=pagina,
        session_id=str(session_id) if session_id else None,
    )

    return JsonResponse({"resposta": resposta})


@login_required
def tela_cheia(request):
    """Versão em página inteira do assistente, pra abrir numa aba separada."""
    return render(request, "assistente_ia/tela_cheia.html")


@login_required
@user_passes_test(lambda u: u.is_staff)
def relatorio_uso(request):
    """Ranking de quem mais usa o assistente — só pra staff."""
    ranking = (
        UsoAssistenteIA.objects.values("analista__username", "analista__first_name")
        .annotate(total=Count("id"), ultima_pergunta=Max("criado_em"))
        .order_by("-total")
    )
    return render(request, "assistente_ia/relatorio_uso.html", {"ranking": ranking})