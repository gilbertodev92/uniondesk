# /whatsapp_bot/ia_fila.py
"""
FILA DE RESPOSTA DA IA — agrupamento de mensagens e trava anti-duplicidade.

O PROBLEMA QUE ISTO RESOLVE
---------------------------
Cliente escreve picotado (digita, Enter, digita, Enter):

    11:21  "Eu preciso tirar os XML de junho..."
    11:21  "Você consegue gerar pra mim?"

Cada mensagem dispara o webhook na hora. As duas eram processadas em
PARALELO, as duas liam "status = TRIAGEM", e as duas respondiam/transferiam
— o cliente recebia duas respostas quase iguais.

(Isso ficava escondido enquanto o gunicorn rodava com 1 worker: as
requisições eram atendidas em fila. Ao ganhar 20 slots simultâneos, a
condição de corrida apareceu.)

COMO RESOLVEMOS
---------------
1. JANELA DE SILÊNCIO (debounce): ao chegar mensagem, a IA NÃO responde na
   hora. Espera alguns segundos. Se o cliente mandar outra nesse intervalo,
   a anterior desiste e quem responde é a última — lendo TODAS juntas.
   É o que uma pessoa faria: espera o outro terminar de escrever.

2. TRAVA POR SESSÃO: só uma resposta por conversa é processada por vez.
   Mesmo que duas cheguem no mesmo milissegundo, uma espera a outra.

O webhook responde ao WhatsApp IMEDIATAMENTE; todo o trabalho da IA
acontece numa thread em segundo plano.
"""
import logging
import threading
import time

from django.utils import timezone

logger = logging.getLogger("rastreador_zap")

# Segundos de silêncio antes de responder. 8s cobre bem quem escreve
# picotado sem deixar o cliente achando que ninguém viu a mensagem.
JANELA_SILENCIO = 8

# Travas em memória, uma por sessão (evita processar a mesma conversa 2x)
_travas = {}
_travas_lock = threading.Lock()


def _obter_trava(session_id):
    with _travas_lock:
        if session_id not in _travas:
            _travas[session_id] = threading.Lock()
        return _travas[session_id]


def agendar_resposta_ia(session_id, message_id_gatilho, remote_jid,
                        base64_media=None, mime_media=None, media_url=None):
    """
    Agenda a resposta da IA para daqui a JANELA_SILENCIO segundos.

    `message_id_gatilho` é o ID (pk) da Message do cliente que disparou esta
    chamada. Depois da espera, se já existir mensagem MAIS NOVA do cliente,
    esta desiste — a mais nova é que vai responder, com o contexto completo.
    """
    t = threading.Thread(
        target=_processar_depois_da_espera,
        args=(session_id, message_id_gatilho, remote_jid,
              base64_media, mime_media, media_url),
        daemon=True,
    )
    t.start()


def _processar_depois_da_espera(session_id, message_id_gatilho, remote_jid,
                                base64_media, mime_media, media_url):
    from django.db import connection
    from .models import ChatSession, Message

    try:
        time.sleep(JANELA_SILENCIO)

        # ── Ainda sou a última mensagem do cliente? ──
        ultima = (
            Message.objects
            .filter(session_id=session_id, sender_type='CLIENTE')
            .order_by('-timestamp', '-id')
            .first()
        )
        if not ultima or ultima.id != message_id_gatilho:
            logger.info(
                f"⏭️ [FILA IA] Mensagem {message_id_gatilho} descartada: "
                f"chegou outra depois. Sessão {session_id}."
            )
            return

        # ── Trava: uma resposta por conversa de cada vez ──
        trava = _obter_trava(session_id)
        if not trava.acquire(blocking=False):
            logger.info(f"🔒 [FILA IA] Sessão {session_id} já está sendo processada. Saindo.")
            return

        try:
            session = ChatSession.objects.filter(pk=session_id).first()
            if not session:
                return

            # a situação pode ter mudado durante a espera (técnico assumiu,
            # cliente foi transferido, atendimento encerrado...)
            if not session.em_atendimento_ia or session.status not in ['TRIAGEM', 'SUPORTE_IA']:
                logger.info(
                    f"⏭️ [FILA IA] Sessão {session_id} saiu do modo IA durante a espera "
                    f"(status={session.status}). Não vou responder."
                )
                return

            texto_junto = _juntar_mensagens_pendentes(session_id)
            if not texto_junto:
                return

            logger.info(
                f"🧵 [FILA IA] Respondendo sessão {session_id} com "
                f"{texto_junto.count(chr(10)) + 1} mensagem(ns) agrupada(s)."
            )

            _responder(session, texto_junto, remote_jid,
                       base64_media, mime_media, media_url)
        finally:
            trava.release()

    except Exception as e:
        logger.error(f"[FILA IA] Falha ao processar sessão {session_id}: {e}")
    finally:
        # thread própria = conexão própria com o banco; fechamos pra não vazar
        try:
            connection.close()
        except Exception:
            pass


def _juntar_mensagens_pendentes(session_id):
    """
    Junta as mensagens do CLIENTE que ainda não foram respondidas — ou seja,
    as que vieram depois da última fala da IA ou do técnico.

    É isso que faz a IA ler "preciso dos XML de junho" + "você consegue gerar
    pra mim?" como UMA coisa só, em vez de duas perguntas soltas.
    """
    from .models import Message

    ultima_resposta = (
        Message.objects
        .filter(session_id=session_id, sender_type__in=['IA', 'TECNICO'])
        .order_by('-timestamp', '-id')
        .first()
    )

    qs = Message.objects.filter(session_id=session_id, sender_type='CLIENTE')
    if ultima_resposta:
        qs = qs.filter(timestamp__gte=ultima_resposta.timestamp).exclude(
            id__lte=ultima_resposta.id
        )

    textos = [m.text.strip() for m in qs.order_by('timestamp', 'id') if m.text and m.text.strip()]
    if not textos:
        return None

    # remove repetições coladas ("oi" / "oi")
    limpos = []
    for t in textos:
        if not limpos or limpos[-1] != t:
            limpos.append(t)

    return "\n".join(limpos)


def _responder(session, texto_cliente, remote_jid, base64_media, mime_media, media_url):
    """Chama a IA e entrega a resposta — mesmo fluxo que o webhook fazia antes."""
    from .bot_engine import processar_triagem_ia
    from .models import Message
    from . import views  # helpers de envio (enviar_msg_whatsapp, conversões...)

    resultado_ia = processar_triagem_ia(
        session, texto_cliente, media_url, base64_media, mime_media
    )

    fala_ia = resultado_ia.get("texto") or resultado_ia.get("texto_ia")
    audio_b64_ia = resultado_ia.get("audio_b64")

    # 1) texto
    if fala_ia:
        views.enviar_msg_whatsapp(remote_jid, fala_ia)
        Message.objects.create(session=session, sender_type='IA', text=fala_ia)

    # 2) áudio (se a IA gerou)
    if audio_b64_ia:
        try:
            views.enviar_audio_ia(session, remote_jid, audio_b64_ia)
        except Exception as e:
            logger.error(f"[FILA IA] Falha ao enviar áudio: {e}")

    # 3) consequências da decisão
    acao = resultado_ia.get("acao")
    if acao == "MENU":
        menu = ("Como posso ajudar?\n\n"
                "1. Suporte Sistemas\n"
                "2. Assistência Equipamentos\n"
                "3. Comercial/Vendas\n"
                "4. Financeiro")
        views.enviar_msg_whatsapp(remote_jid, menu)
        Message.objects.create(session=session, sender_type='IA', text=menu)
        session.status = 'PENDENTE'
        session.em_atendimento_ia = False
        session.save()
    elif acao == "TRANSFERIR":
        session.setor_atual = resultado_ia.get("setor")
        session.status = 'PENDENTE'
        session.em_atendimento_ia = False
        session.save()

    session.ultima_interacao = timezone.now()
    session.save()
