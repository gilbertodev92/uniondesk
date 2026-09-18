import json
import requests
import re
import uuid
import base64
import os
import tempfile
import subprocess
import threading
import time 

from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Avg, Count, Q

from .models import ChatSession, Message, TagAtendimento, MensagemRapida, BotConfig
# Importamos a IA, mas também exportamos as funções de áudio para ela usar
from .bot_engine import processar_triagem_ia, processar_notas_cs
from clientes_sistemas.models import Cliente
from cs_satisfacao.models import EventoCS
from recompensas.utils import processar_acao_gamificada
import spacy
# Carrega a IA de gramática em português (fica fora das funções para não deixar o sistema lento)
try:
    nlp = spacy.load("pt_core_news_sm")
except:
    nlp = None

User = get_user_model()

# ==============================================================================
# CONFIGURAÇÕES DA EVOLUTION API
# ==============================================================================
from django.conf import settings

EVOLUTION_API_URL = settings.EVOLUTION_API_URL
EVOLUTION_API_KEY = settings.EVOLUTION_API_KEY
INSTANCE_NAME = settings.EVOLUTION_INSTANCE

def enviar_msg_whatsapp(number, texto):
    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendText/{INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    
    tempo_digitando = max(1500, min(len(texto) * 30, 4000))
    
    payload = {"number": number, "text": texto, "delay": tempo_digitando}
    try: 
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e: 
        print(f"[ERRO ENVIO MSG IA/SISTEMA] {e}", flush=True)

def obter_destino_seguro(number):
    if "@g.us" in number: return number
    safe_number = re.sub(r'\D', '', number.split('@')[0])
    return f"{safe_number}@lid" if len(safe_number) >= 14 else f"{safe_number}@s.whatsapp.net"

def buscar_foto_perfil(number):
    url = f"{EVOLUTION_API_URL.rstrip('/')}/chat/fetchProfilePictureUrl/{INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json={"number": number}, headers=headers, timeout=5)
        if response.status_code == 200: return response.json().get('profilePictureUrl')
    except: 
        pass
    return None

def baixar_midia_evolution(event_data):
    url = f"{EVOLUTION_API_URL.rstrip('/')}/chat/getBase64FromMediaMessage/{INSTANCE_NAME}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json={"message": event_data}, headers=headers, timeout=20)
        if response.status_code in [200, 201]: return response.json().get('base64')
    except Exception as e: 
        print(f"[ERRO API MIDIA] {e}", flush=True)
    return None

def salvar_midia_fisica(b64_string, mimetype, nome_arquivo):
    try:
        if not b64_string: return None
        if b64_string.startswith('data:'): b64_string = b64_string.split(',')[1]
        file_data = base64.b64decode(b64_string)
        ext = mimetype.split('/')[-1].split(';')[0]
        if ext == 'octet-stream': ext = 'bin'
        if ext == 'vnd.whatsapp.audio': ext = 'ogg'
        nome_limpo = re.sub(r'[^a-zA-Z0-9_\-\.]', '', str(nome_arquivo).replace(' ', '_'))
        if not nome_limpo: nome_limpo = "midia"
        file_name = f"whatsapp/{uuid.uuid4().hex[:8]}_{nome_limpo}.{ext}"
        path = default_storage.save(file_name, ContentFile(file_data))
        return default_storage.url(path)
    except Exception as e:
        print(f"[ERRO SALVAR FISICO] {e}", flush=True)
        return None

def converter_para_mp4_whatsapp(file_bytes):
    temp_in_path = ""
    temp_out_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_in:
            temp_in.write(file_bytes)
            temp_in_path = temp_in.name
        temp_out_path = temp_in_path + "_out.mp4"
        # CIRURGIA: Caminho absoluto do FFmpeg
        comando = ['/usr/bin/ffmpeg', '-y', '-i', temp_in_path, '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-f', 'mp4', temp_out_path]
        subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        with open(temp_out_path, 'rb') as f: converted_bytes = f.read()
        os.remove(temp_in_path)
        os.remove(temp_out_path)
        return converted_bytes
    except Exception:
        if os.path.exists(temp_in_path): os.remove(temp_in_path)
        if os.path.exists(temp_out_path): os.remove(temp_out_path)
        return file_bytes

def converter_para_mp3_whatsapp(file_bytes):
    print("[LOG AUDIO] Iniciando conversão FFmpeg RAW PCM para MP3...", flush=True)
    temp_in_path = ""
    temp_out_path = ""
    try:
        # Salvamos o arquivo cru como .pcm para não confundir o sistema
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pcm") as temp_in:
            temp_in.write(file_bytes)
            temp_in_path = temp_in.name
        temp_out_path = temp_in_path + "_out.mp3"
        
        # A MÁGICA: Ensinamos pro FFmpeg que o arquivo de entrada é RAW PCM 16-bit 24kHz Mono!
        comando = [
            '/usr/bin/ffmpeg', '-y', 
            '-f', 's16le', '-ar', '24000', '-ac', '1', 
            '-i', temp_in_path, 
            '-c:a', 'libmp3lame', '-q:a', '2', 
            temp_out_path
        ]
        subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        with open(temp_out_path, 'rb') as f: 
            converted_bytes = f.read()
            
        os.remove(temp_in_path)
        os.remove(temp_out_path)
        print("[LOG AUDIO] Conversão MP3 concluída com sucesso!", flush=True)
        return converted_bytes
    except Exception as e:
        print(f"[ERRO FFMPEG MP3] Falha na conversão: {e}", flush=True)
        if os.path.exists(temp_in_path): os.remove(temp_in_path)
        if os.path.exists(temp_out_path): os.remove(temp_out_path)
        return file_bytes

# ==============================================================================
# INTELIGÊNCIA DE ROTEAMENTO E AUTO-CURA MATADORA
# ==============================================================================
def extrair_ddd_e_numero(numero_bruto):
    n = re.sub(r'\D', '', str(numero_bruto))
    if n.startswith('55') and len(n) >= 10: n = n[2:] 
    if n.startswith('0'): n = n[1:] 
    if len(n) <= 9: 
        if len(n) == 9 and n.startswith('9'): return "", n[1:]
        return "", n
    ddd = n[:2]
    resto = n[2:]
    if len(resto) == 9 and resto.startswith('9'): resto = resto[1:] 
    return ddd, resto



def extrair_numero_real_do_key(key_data):
    if not key_data or not isinstance(key_data, dict): return None
    if key_data.get('remoteJidAlt') and '@s.whatsapp.net' in key_data.get('remoteJidAlt'): return key_data.get('remoteJidAlt')
    if key_data.get('participantAlt') and '@s.whatsapp.net' in key_data.get('participantAlt'): return key_data.get('participantAlt')
    if key_data.get('participant') and '@s.whatsapp.net' in key_data.get('participant'): return key_data.get('participant')
    if key_data.get('remoteJid') and '@s.whatsapp.net' in key_data.get('remoteJid'): return key_data.get('remoteJid')
    return None



def normalizar_jid(remote_jid_raw, event_data):
    if not remote_jid_raw: return ""
    if "@g.us" in remote_jid_raw: return remote_jid_raw 
    
    real_id = remote_jid_raw
    possiveis_ids = [remote_jid_raw, event_data.get('key', {}).get('participant', ''), event_data.get('participant', ''), event_data.get('sender', '')]
    for pid in possiveis_ids:
        if pid and "@s.whatsapp.net" in pid:
            real_id = pid
            break
            
    numero_limpo = re.sub(r':\d+', '', real_id.split('@')[0])
    
    if "@s.whatsapp.net" in real_id: return f"{numero_limpo}@s.whatsapp.net"
    elif "@lid" in real_id: return f"{numero_limpo}@lid"
    else: return f"{numero_limpo}@lid" if len(numero_limpo) >= 14 else f"{numero_limpo}@s.whatsapp.net"

def buscar_ou_criar_cliente(whatsapp_number):
    ddd, num_base = extrair_ddd_e_numero(whatsapp_number.split('@')[0])
    if num_base and len(num_base) >= 8:
        cliente = Cliente.objects.filter(telefone__icontains=num_base).first()
        if not cliente: cliente = Cliente.objects.filter(telefone_responsavel__icontains=num_base).first()
        if cliente: return cliente
    final_number = re.sub(r':\d+', '', whatsapp_number.split('@')[0])
    if 8 <= len(final_number) <= 13: 
        cliente = Cliente.objects.filter(telefone__icontains=final_number[-8:]).first()
        if not cliente: cliente = Cliente.objects.filter(telefone_responsavel__icontains=final_number[-8:]).first()
        return cliente
    return None

def obter_sessao_ativa(remote_jid, is_group, cliente=None):
    sessoes_q = ChatSession.objects.exclude(status='FINALIZADO')

    if is_group:
        sessoes = list(sessoes_q.filter(whatsapp_number=remote_jid).order_by('id'))
    else:
        numero_puro = re.sub(r'\D', '', remote_jid.split('@')[0])
        filtro = Q(whatsapp_number=remote_jid)
        
        if len(numero_puro) >= 8:
            # 🔥 CORREÇÃO BRASIL: Busca sempre pelos últimos 8 dígitos ignorando o 9º dígito
            chave_busca = numero_puro[-8:]
            filtro |= Q(whatsapp_number__icontains=chave_busca)
            
        # O filtro de cliente foi removido. 
        # Agora o sistema isola o chat ESTRITAMENTE pelo número do WhatsApp.
        # Uma mesma empresa pode ter 10 números conversando em 10 abas separadas.
            
        sessoes = list(sessoes_q.filter(filtro).order_by('id'))

    if not sessoes:
        return None

    if len(sessoes) == 1:
        sessao_unica = sessoes[0]
        if cliente and not sessao_unica.cliente:
            sessao_unica.cliente = cliente
            sessao_unica.save(update_fields=['cliente'])
        return sessao_unica

    sessao_principal = None
    for s in sessoes:
        if s.tecnico_responsavel:
            sessao_principal = s
            break
    if not sessao_principal:
        sessao_principal = sessoes[0]
    
    with transaction.atomic():
        for s in sessoes:
            if s.id != sessao_principal.id:
                mensagens = Message.objects.filter(session=s)
                for msg in mensagens:
                    try:
                        with transaction.atomic():
                            msg.session = sessao_principal
                            msg.save()
                    except Exception:
                        msg.delete()
                
                s.status = 'FINALIZADO'
                s.em_atendimento_ia = False
                s.save(update_fields=['status', 'em_atendimento_ia'])
    
    if cliente and not sessao_principal.cliente:
        sessao_principal.cliente = cliente
        sessao_principal.save(update_fields=['cliente'])
        
    return sessao_principal

def get_setor_tecnico(user):
    setores_validos = ['SUPORTE', 'COMERCIAL', 'FINANCEIRO', 'ASSISTENCIA']
    if hasattr(user, 'setor') and str(user.setor).upper() in setores_validos: return str(user.setor).upper()
    for group in user.groups.all():
        g_name = group.name.upper()
        for s in setores_validos:
            if s in g_name: return s
    return "SUPORTE"

def enviar_audio_ia(session, remote_jid, audio_b64_ia):
    """
    Converte o áudio gerado pela IA (PCM/WAV do Gemini) para MP3, salva o
    arquivo físico (pro player do painel) e envia pro WhatsApp via Evolution.

    Extraído do webhook para poder ser chamado também pela fila da IA
    (ia_fila.py), que agora é quem processa as respostas em segundo plano.
    """
    try:
        print("[LOG PASSO 1] Áudio recebido do Gemini. Iniciando processamento...", flush=True)

        b64_puro_audio = audio_b64_ia.split('base64,')[-1] if 'base64,' in audio_b64_ia else audio_b64_ia
        wav_bytes = base64.b64decode(b64_puro_audio)

        mp3_bytes = converter_para_mp3_whatsapp(wav_bytes)
        b64_mp3 = base64.b64encode(mp3_bytes).decode('utf-8')

        # etiqueta MP3 só para salvar no painel e renderizar o player
        b64_salvar = f"data:audio/mp3;base64,{b64_mp3}"

        print("[LOG PASSO 2] Salvando arquivo físico na pasta media do Django...", flush=True)
        # a palavra "audio" no nome do arquivo ativa o player de voz no painel
        url_fisica_ia = salvar_midia_fisica(b64_salvar, 'audio/mp3', 'audio_ia')

        if not url_fisica_ia:
            print("[ERRO PASSO 2] Falha ao salvar a mídia física. Abortando envio de voz.", flush=True)
            return False

        print("[LOG PASSO 3] Enviando áudio para a API da Evolution...", flush=True)
        url_audio = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendWhatsAppAudio/{INSTANCE_NAME}"
        payload_audio = {"number": remote_jid, "audio": b64_mp3}
        headers_evo = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

        res_evo = requests.post(url_audio, json=payload_audio, headers=headers_evo, timeout=45)
        print(f"[LOG PASSO 4] Retorno Evolution: Status {res_evo.status_code}", flush=True)

        if res_evo.status_code in [200, 201]:
            # "🎤 Áudio" ativa as travas do frontend
            Message.objects.create(session=session, sender_type='IA',
                                   text="🎤 Áudio", media_url=url_fisica_ia)
            print("[LOG SUCESSO] Player de áudio criado no painel e mensagem despachada!", flush=True)
            return True

        print(f"[ERRO FATAL EVOLUTION] Status: {res_evo.status_code} | Msg: {res_evo.text}", flush=True)
        return False

    except Exception as e:
        print(f"\n[CRITICAL FALHA ÁUDIO IA] Interrupção no meio do processo: {e}\n", flush=True)
        return False


@csrf_exempt
def whatsapp_webhook(request):
    import logging
    logger = logging.getLogger('rastreador_zap')
    
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            
            # 🔥 LOG NA PORTA DE ENTRADA: Registra TUDO que a Evolution manda!
            evento_recebido = data.get('event', 'DESCONHECIDO')
            logger.info(f"🚪 [WEBHOOK BATEU] Evento: {evento_recebido}")
            
            if isinstance(data, list): return JsonResponse({'status': 'ignored_list_event'})
            
            event_type = data.get('event')
            event_data = data.get('data', {})
            
            # 🔥 LOG SE FOR MENSAGEM: Mostra o ID da mensagem para vermos se duplicou
            if event_type == 'messages.upsert':
                msg_id = event_data.get('key', {}).get('id', 'SemID')
                remetente = event_data.get('key', {}).get('remoteJid', 'Desconhecido')
                logger.info(f"📨 [MENSAGEM RECEBIDA] ID: {msg_id} | De: {remetente}")
                logger.info(f"🕵️ DUMP COMPLETO DO WHATSAPP: {json.dumps(event_data)}")
            
           # --- ATUALIZAR STATUS DE LEITURA (TICKS) BLINDADO ---
            if event_type in ['messages.update', 'message.status', 'message.update']:
                items = event_data if isinstance(event_data, list) else [event_data]
                for item in items:
                    # 1. Pega TODOS os IDs possíveis que a Evolution pode mandar
                    ids_para_buscar = []
                    for k in ['keyId', 'id', 'messageId']:
                        if item.get(k): ids_para_buscar.append(item.get(k))
                    if item.get('key', {}).get('id'):
                        ids_para_buscar.append(item.get('key', {}).get('id'))
                    
                    # Limpa IDs vazios e repetidos
                    ids_para_buscar = list(set(filter(None, ids_para_buscar)))

                    # 2. Pega o status
                    upd_status = item.get('status') or item.get('update', {}).get('status')

                    if ids_para_buscar and upd_status is not None:
                        status_map = {'DELIVERY_ACK': 2, '2': 2, 'DELIVERED': 2, 'READ': 3, '3': 3, 'VIEWED': 3, 'PLAYED': 4, '4': 4}
                        status_num = status_map.get(str(upd_status).upper(), 1)
                        
                        # 3. Busca no banco combinando qualquer um dos IDs
                        query = Q()
                        for pid in ids_para_buscar:
                            query |= Q(message_id__icontains=pid)
                            
                        msg = Message.objects.filter(query).first()
                        
                        # 4. A MÁGICA: Só atualiza se o novo status for MAIOR que o atual
                        # Evita que um aviso atrasado de "Entregue (2)" apague o "Lido (3)"
                        if msg and status_num > getattr(msg, 'ack', 0):
                            msg.ack = status_num
                            msg.save(update_fields=['ack'])
                            
                return JsonResponse({'status': 'ack_updated'})


            if event_type != 'messages.upsert' and event_type != '':
                if 'messages.upsert' not in event_type:
                    return JsonResponse({'status': 'event_ignored'})
            
            key = event_data.get('key', {})
            from_me = key.get('fromMe', False)
            message_id = key.get('id', '')
            push_name = event_data.get('pushName', '')
            message_obj = event_data.get('message', {})

            remote_jid_raw = key.get('remoteJid', '')
            
            # 🔥 1. TRADUTOR DE LID (OBRIGATÓRIO): Converte o ID esquisito da Evolution para o WhatsApp real
            if not from_me and "@g.us" not in remote_jid_raw:
                numero_de_verdade = extrair_numero_real_do_key(key)
                if numero_de_verdade:
                    remote_jid_raw = numero_de_verdade
                    logger.info(f"🕵️ Número real extraído com SUCESSO: {remote_jid_raw}")

            # 🛡️🔥 2. ESCUDO ANTIMÍSSIL DEFINITIVO: Impede que a IA atenda os próprios técnicos
            if not from_me and "@g.us" not in remote_jid_raw:
                num_limpo = re.sub(r'\D', '', remote_jid_raw.split('@')[0])[-8:]
                if num_limpo:
                    # Delega a busca pro Banco de Dados
                    is_employee = User.objects.filter(is_active=True, profile__phone_e164__icontains=num_limpo).exists()
                    
                    if is_employee:
                        logger.info(f"🛡️ [TRAVA ANTIMÍSSIL] Mensagem de {push_name} ignorada para evitar autoatendimento.")
                        return JsonResponse({'status': 'ignored_employee'})

            # 🔥 3. TRAVA DE DUPLICIDADE 
            if message_id and Message.objects.filter(message_id__icontains=message_id).exists():
                return JsonResponse({'status': 'ignored_duplicate_webhook'})
            
           # =========================================================
            # EXTRAÇÃO DO CONTATO (BLINDADO E SIMPLES)
            # =========================================================
            message_text = ""
            
            if 'conversation' in message_obj:
                message_text = message_obj['conversation']
            elif 'extendedTextMessage' in message_obj:
                message_text = message_obj['extendedTextMessage'].get('text', '')
            elif 'locationMessage' in message_obj:
                loc = message_obj['locationMessage']
                message_text = f"📍 MAPA|{loc.get('degreesLatitude')},{loc.get('degreesLongitude')}"
            
            # =========================================================
            # EXTRAÇÃO DO CONTATO (BLINDADO E DEFINITIVO)
            # =========================================================
            elif 'contactMessage' in message_obj:
                vcard = message_obj['contactMessage'].get('vcard', '')
                c_name = message_obj['contactMessage'].get('displayName', 'Contato')
                
                # Busca o número nos padrões Android e iOS
                match_waid = re.search(r'waid=(\d+)', vcard)
                if match_waid:
                    c_num_limpo = match_waid.group(1)
                else:
                    numeros = re.findall(r'TEL.*?:([+\d\s\-\(\)]+)', vcard)
                    c_num_limpo = re.sub(r'\D', '', numeros[0]) if numeros else ""
                
               # Trata DDD e DDI
                if c_num_limpo.startswith('0'): c_num_limpo = c_num_limpo[1:]
                if len(c_num_limpo) == 10 or len(c_num_limpo) == 11: 
                    c_num_limpo = f"55{c_num_limpo}"
                
                # SALVA ASSIM: Simples, com separador e um \n para quebrar no HTML 
                message_text = f"👤 CONTATO | | {c_name}\n +{c_num_limpo}"

            quoted_text = None
            quoted_id = None
            context_info = None
            
            for k, v in message_obj.items():
                if isinstance(v, dict) and 'contextInfo' in v:
                    context_info = v['contextInfo']
                    break
                    
            if not context_info and 'contextInfo' in message_obj:
                context_info = message_obj['contextInfo']
            if not context_info and 'contextInfo' in event_data:
                context_info = event_data['contextInfo']
                    
            if context_info:
                quoted_id = context_info.get('stanzaId')
                q_msg = context_info.get('quotedMessage', {})
                if q_msg:
                    quoted_text = q_msg.get('conversation') or \
                                  q_msg.get('extendedTextMessage', {}).get('text') or \
                                  q_msg.get('text')
                    
                    if not quoted_text:
                        if 'imageMessage' in q_msg: quoted_text = q_msg['imageMessage'].get('caption', '📷 Imagem')
                        elif 'videoMessage' in q_msg: quoted_text = "🎥 Vídeo"
                        elif 'audioMessage' in q_msg: quoted_text = "🎤 Áudio"
                        elif 'documentMessage' in q_msg: quoted_text = "📎 Arquivo"
                        else: quoted_text = "Mensagem citada"
            
            if quoted_text:
                quoted_text = str(quoted_text)
                quoted_text = quoted_text[:250] + "..." if len(quoted_text) > 250 else quoted_text

            msg_type = 'conversation'
            is_media = False
            if 'imageMessage' in message_obj: msg_type = 'imageMessage'; is_media = True
            elif 'videoMessage' in message_obj: msg_type = 'videoMessage'; is_media = True
            elif 'audioMessage' in message_obj: msg_type = 'audioMessage'; is_media = True
            elif 'documentMessage' in message_obj: msg_type = 'documentMessage'; is_media = True

            if not message_text and not is_media: return JsonResponse({'status': 'ignored'})

            remote_jid = normalizar_jid(remote_jid_raw, event_data)
            is_group = "@g.us" in remote_jid
            cliente = buscar_ou_criar_cliente(remote_jid) if not is_group else None
            
            if is_group and not from_me and not is_media:
                remetente_grupo = push_name or "Membro"
                message_text = f"👤 _{remetente_grupo}_:\n{message_text}"

            session = obter_sessao_ativa(remote_jid, is_group, cliente)
            created = False
            
            if session:
                if "@lid" in session.whatsapp_number and "@s.whatsapp.net" in remote_jid:
                    session.whatsapp_number = remote_jid
                    session.save(update_fields=['whatsapp_number'])
            else:
                # SE FOR GRUPO, DEIXA CRIAR A SESSÃO MESMO SE A PRIMEIRA MENSAGEM FOR NOSSA
                if from_me and not is_group: return JsonResponse({'status': 'ignored_ghost_echo'})
                
                time.sleep(0.4)
                session_check = obter_sessao_ativa(remote_jid, is_group, cliente)
                
                if not session_check:
                    with transaction.atomic():
                        session = ChatSession.objects.create(
                            whatsapp_number=remote_jid, 
                            cliente=cliente, 
                            mensagens_nao_lidas=1 if not from_me else 0, # Se fomos nós que enviamos, não fica não lida
                            status='EM_ATENDIMENTO' if is_group else 'TRIAGEM', # Grupo já nasce em atendimento
                            em_atendimento_ia=not is_group # IA não atende grupo por padrão
                        )
                        created = True
                else:
                    session = session_check
                
                         
            if not created and not from_me: 
                session.mensagens_nao_lidas = getattr(session, 'mensagens_nao_lidas', 0) + 1 
                
            if not session.cliente and cliente: 
                session.cliente = cliente

            if push_name and session.push_name != push_name and not is_group:
                session.push_name = push_name
            
            # 🔥 A TÁTICA OPORTUNISTA: O "Limpador Invisível" de Fotos
            def atualizar_foto_silenciosa(sess_id, jid):
                from django.db import connection
                try:
                    nova_foto = buscar_foto_perfil(jid)
                    if nova_foto:
                        ChatSession.objects.filter(id=sess_id).update(profile_pic=nova_foto)
                except: 
                    pass
                finally: 
                    connection.close() # Evita travar o banco de dados do Django
                
            # Se a sessão for nova ou estiver sem foto nenhuma, trava e busca na hora
            if created or not session.profile_pic:
                foto_url = buscar_foto_perfil(remote_jid_raw)
                if foto_url: session.profile_pic = foto_url
            # Se for uma mensagem do cliente (e não nossa), manda o Trabalhador Invisível conferir a foto por trás dos panos!
            elif not from_me:
                import threading
                threading.Thread(target=atualizar_foto_silenciosa, args=(session.id, remote_jid_raw)).start()
                    
            session.save()

            media_url = None
            sender_type = 'TECNICO' if from_me else 'CLIENTE'
            b64_puro = None
            mimetype = None
            
            if is_media:
                b64_puro = baixar_midia_evolution(event_data)
                if b64_puro:
                    mimetype = message_obj[msg_type].get('mimetype', 'application/octet-stream')
                    file_name = message_obj[msg_type].get('fileName', f'arquivo_{msg_type}')
                    b64_full_for_save = f"data:{mimetype};base64,{b64_puro}"
                    media_url = salvar_midia_fisica(b64_full_for_save, mimetype, file_name)

                remetente_str = f"👤 _{push_name}_:\n" if is_group and not from_me else ""
                
                if not message_text:
                    if msg_type == 'imageMessage': 
                        caption = message_obj[msg_type].get('caption', '')
                        message_text = f"{remetente_str}📷 Imagem. {caption}".strip()
                    elif msg_type == 'videoMessage': 
                        message_text = f"{remetente_str}🎥 Vídeo"
                    elif msg_type == 'audioMessage': 
                        message_text = f"{remetente_str}🎤 Áudio"
                    elif msg_type == 'documentMessage': 
                        message_text = f"{remetente_str}📎 Arquivo: {message_obj[msg_type].get('fileName', 'Documento')}"

            if from_me and sender_type == 'TECNICO':
                recente = Message.objects.filter(session=session, sender_type='TECNICO', text=message_text, timestamp__gte=timezone.now() - timedelta(seconds=15)).exists()
                if recente: return JsonResponse({'status': 'ignored_duplicate'})

            tecnico_msg = session.tecnico_responsavel if from_me and hasattr(session, 'tecnico_responsavel') else None

            # 🔥 INTERCEPTADOR DE TÉCNICOS NO GRUPO (Zero Delay)
            # Só pesquisa se for mensagem de grupo e não for enviada pelo próprio robô
            if is_group and not from_me:
                remetente_real = key.get('participant') or event_data.get('participant', '')
                if remetente_real:
                    num_remetente = re.sub(r'\D', '', remetente_real.split('@')[0])[-8:]
                    if num_remetente:
                        # Comparação feita em Python (não no banco): phone_e164 pode estar
                        # salvo com formatação, ex: "(47) 98902-0590" — o "icontains" direto
                        # no banco quebra nesse caso, porque o hífen interrompe a sequência
                        # de dígitos e o número nunca "bate" com o participante do grupo.
                        tec_oculto = None
                        candidatos = User.objects.filter(
                            is_active=True, profile__phone_e164__isnull=False
                        ).exclude(profile__phone_e164='').select_related('profile')
                        for u in candidatos:
                            numero_cadastrado = re.sub(r'\D', '', u.profile.phone_e164)
                            if numero_cadastrado and numero_cadastrado[-8:] == num_remetente:
                                tec_oculto = u
                                break
                        if tec_oculto:
                            sender_type = 'TECNICO'
                            tecnico_msg = tec_oculto

            dna_id = f"{remote_jid}|{message_id}"

            try:
                msg_salva = Message.objects.create(session=session, sender_type=sender_type, text=message_text, media_url=media_url, message_id=dna_id, quoted_message_id=quoted_id, quoted_text=quoted_text, tecnico=tecnico_msg)
            except Exception:
                msg_salva = Message.objects.create(session=session, sender_type=sender_type, text=message_text, media_url=media_url, tecnico=tecnico_msg)
                
            if hasattr(msg_salva, 'ack'): 
                msg_salva.ack = 1
                msg_salva.save()

            if not from_me and not is_group:
                
                if session.status == 'PENDENTE' and not session.tecnico_responsavel and not session.em_atendimento_ia:
                    texto_limpo = message_text.strip()
                    opcoes_menu = {"1": "SUPORTE", "2": "ASSISTENCIA", "3": "COMERCIAL", "4": "FINANCEIRO"}
                    if texto_limpo in opcoes_menu:
                        session.setor_atual = opcoes_menu[texto_limpo]
                        session.save()
                        txt_confirma = f"✅ Direcionado para a fila de *{session.get_setor_atual_display()}*. O próximo especialista livre vai te atender."
                        enviar_msg_whatsapp(remote_jid, txt_confirma)
                        Message.objects.create(session=session, sender_type='SISTEMA', text=txt_confirma)
                        return JsonResponse({'status': 'success'})

                # =========================================================================
                # LÓGICA DE REABERTURA OU IGNORAR MENSAGENS CURTAS PÓS-ATENDIMENTO
                # =========================================================================
                if session.status in ['AVALIACAO_TECNICO', 'AVALIACAO_NPS', 'FINALIZADO']:
                    sucesso = processar_notas_cs(session, message_text)
                    
                    if sucesso:
                        if session.status == 'AVALIACAO_NPS':
                            enviar_msg_whatsapp(remote_jid, "Obrigado! Para finalizarmos: de 0 a 10, o quanto você recomendaria a nossa empresa?")
                            Message.objects.create(session=session, sender_type='SISTEMA', text="Pediu nota de NPS (0 a 10).")
                            
                   
                         # =========================================================
                            # GAMIFICAÇÃO: PONTUAR SE A NOTA DO TÉCNICO FOI 5 ESTRELAS
                            # =========================================================
                            try:
                                if getattr(session, 'nota_tecnico', 0) == 5 and session.tecnico_responsavel:
                                    from recompensas.utils import processar_acao_gamificada
                                    identificador = session.cliente.razao_social if session.cliente else session.whatsapp_number.split('@')[0]
                                    processar_acao_gamificada(
                                        usuario=session.tecnico_responsavel, 
                                        acao='feedback_5_estrelas',
                                        detalhe=f"Cliente: {identificador}"
                                    )
                            except Exception as e:
                                print(f"Erro Gamificação 5 Estrelas: {e}")

                        elif session.status == 'FINALIZADO':
                            enviar_msg_whatsapp(remote_jid, "Avaliação registrada. Muito obrigado pela parceria! 🚀")
                            Message.objects.create(session=session, sender_type='SISTEMA', text="Atendimento avaliado e encerrado.")
                            
                            if session.cliente: 
                                try:
                                    # 🔥 PEGA O NOME DO TÉCNICO PARA SALVAR NO CS!
                                    nome_tec = session.tecnico_responsavel.first_name if session.tecnico_responsavel else "Atendimento/Fila"
                                    
                                    EventoCS.objects.create(
                                        cliente=session.cliente,
                                        responsavel=session.tecnico_responsavel,
                                        tipo_contato="FOLLOWUP",
                                        status="REALIZADO",
                                        data_prevista=timezone.now().date(),
                                        data_realizada=timezone.now().date(),
                                        # 🔥 O TEXTO AGORA CARREGA A ASSINATURA DE AUDITORIA DO ATENDIMENTO!
                                        observacoes=f"Atendimento via WhatsApp Finalizado.\nNota do Técnico: {session.nota_tecnico}\nNota NPS: {session.nota_nps}\n---\nTécnico Responsável: {nome_tec.upper()}",
                                    )
                                except Exception as e: 
                                    print(f"[ERRO AO CRIAR EVENTO DE NOTA NO CS] {e}")
                                session.cliente.calcular_health_score()
                        return JsonResponse({'status': 'success'})
                        
                    else:
                        # --- NOVA LÓGICA: CHECA SE É MENSAGEM NOVA OU SÓ UM "OK" ---
                        texto_lower = message_text.lower().strip()
                        mensagens_irrelevantes = ['ok', 'obrigado', 'obrigada', 'vlw', 'valeu', 'show', 'blz', 'beleza', '👍', '🙏', 'certo', 'perfeito']
                        
                        tempo_passado = timedelta(0)
                        ultima_interacao = getattr(session, 'ultima_interacao', None)
                        if ultima_interacao:
                            tempo_passado = timezone.now() - ultima_interacao
                        
                        eh_irrelevante = texto_lower in mensagens_irrelevantes or len(texto_lower) < 3

                        # Se mandou "ok" ou emoji em menos de 2 horas (7200s), ignora e mantém fechado
                        if eh_irrelevante and tempo_passado.total_seconds() < 7200:
                            if session.status != 'FINALIZADO':
                                session.status = 'FINALIZADO'
                                session.save()
                            Message.objects.create(session=session, sender_type='SISTEMA', text="Mensagem de agradecimento ou irrelevante recebida e arquivada.")
                            return JsonResponse({'status': 'success'})
                            
                        else:
                            # Se for uma mensagem real (ou já passou muito tempo), REABRE O CHAMADO!
                            session.status = 'TRIAGEM'
                            session.tecnico_responsavel = None
                            session.em_atendimento_ia = True
                            session.save()
                            Message.objects.create(session=session, sender_type='SISTEMA', text="🔄 Atendimento reaberto automaticamente após nova mensagem.")
                            
                            # 🔥 CIRURGIA 1: Removemos o 'return' e a chamada fantasma que estavam aqui.
                            # Agora deixamos o código fluir para baixo naturalmente. O bloco da IA
                            # vai processar a mensagem, gerar o áudio/texto e mandar pro Zap de verdade!

                if session.em_atendimento_ia and session.status in ['TRIAGEM', 'SUPORTE_IA']:

                    # ═══════════════════════════════════════════════════════════
                    # A IA NÃO RESPONDE MAIS NA HORA.
                    #
                    # A resposta é agendada com uma JANELA DE SILÊNCIO (ver
                    # ia_fila.py). Se o cliente estiver escrevendo picotado
                    # ("preciso do XML" / "consegue gerar pra mim?"), a IA espera
                    # ele terminar e responde UMA vez, lendo tudo junto — em vez
                    # de responder duas vezes, cada uma sem o contexto completo.
                    #
                    # O webhook devolve OK ao WhatsApp na hora; o trabalho da IA
                    # roda numa thread em segundo plano.
                    # ═══════════════════════════════════════════════════════════
                    from .ia_fila import agendar_resposta_ia

                    agendar_resposta_ia(
                        session_id=session.id,
                        message_id_gatilho=msg_salva.id if msg_salva else None,
                        remote_jid=remote_jid,
                        base64_media=b64_puro if is_media else None,
                        mime_media=mimetype if is_media else None,
                        media_url=media_url,
                    )


            session.ultima_interacao = timezone.now()
            session.save()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            print(f"[WEBHOOK ERRO GERAL] {e}", flush=True)
            return JsonResponse({'status': 'error'}, status=500)
    return JsonResponse({'status': 'forbidden'}, status=403)
@login_required
def home(request):
    return render(request, 'whatsapp_bot/home.html')

@login_required
def chat_dashboard(request):
    # 1. FIM DO CARREGAMENTO INFINITO (Limitado às últimas 150 conversas no painel)
    sessions = ChatSession.objects.all().order_by('-ultima_interacao')[:150]
    
    tecnicos = User.objects.filter(is_active=True).values('id', 'first_name', 'last_name')
    clientes = Cliente.objects.all().order_by('razao_social')
    tags_atendimento = TagAtendimento.objects.all().order_by('nome')
    
    try:
        mensagens_rapidas = list(MensagemRapida.objects.all().values('titulo', 'atalho', 'texto'))
        mensagens_rapidas_json = json.dumps(mensagens_rapidas)
    except:
        mensagens_rapidas_json = "[]"

    try:
        active_chats = ChatSession.objects.exclude(status='FINALIZADO')
        total_backlog = active_chats.count()
        
        # Correção de timezone para usar o índice do banco nas buscas de data
        agora = timezone.now()
        hoje = agora.date()
        trinta_dias_atras = agora - timedelta(days=30)

        volume_30d = ChatSession.objects.filter(ultima_interacao__gte=trinta_dias_atras).count()

        fila_espera_count = active_chats.filter(status='PENDENTE').count()
        triagem_ia_count = active_chats.filter(status__in=['TRIAGEM', 'SUPORTE_IA']).count()
        
        # 2. OTIMIZAÇÃO DO ASSASSINO SILENCIOSO (Filtro de texto "icontains")
        # Adicionado limite de 30 dias para o banco não pesquisar em mensagens de anos atrás
        zumbis_mortos_count = Message.objects.filter(
            timestamp__gte=trinta_dias_atras,
            sender_type='SISTEMA', 
            text__icontains='Encerrado silenciosamente'
        ).count()

        labels_vol = []
        dados_vol = []
        
        # 3. OTIMIZAÇÃO DO GRÁFICO (Substituindo __date por range para usar o Index do DB)
        for i in range(6, -1, -1):
            dia = hoje - timedelta(days=i)
            inicio_dia = timezone.make_aware(timezone.datetime.combine(dia, timezone.datetime.min.time()))
            fim_dia = inicio_dia + timedelta(days=1)
            
            labels_vol.append(dia.strftime('%d/%m'))
            count_dia = Message.objects.filter(timestamp__gte=inicio_dia, timestamp__lt=fim_dia).values('session').distinct().count()
            dados_vol.append(count_dia)

        # O restante do código de cálculos continua igual...
        labels_equipe = []
        dados_carga = []
        
        carga_tecnicos = active_chats.exclude(tecnico_responsavel__isnull=True).values(
            'tecnico_responsavel__first_name', 
            'tecnico_responsavel__username'
        ).annotate(total=Count('id')).order_by('-total')
        
        for item in carga_tecnicos:
            nome_tec = item['tecnico_responsavel__first_name'] or item['tecnico_responsavel__username']
            if nome_tec:
                labels_equipe.append(nome_tec.upper())
                dados_carga.append(item['total'])

        health_score_avg = Cliente.objects.aggregate(avg_score=Avg('health_score'))['avg_score'] or 0
        
        risco_critico = Cliente.objects.filter(nivel_risco__in=['ALTO', 'CRITICO']).count()
        risco_atencao = Cliente.objects.filter(nivel_risco='MEDIO').count()
        risco_baixo = Cliente.objects.filter(nivel_risco='BAIXO').count()
        
        labels_risco = ["Risco Crítico", "Atenção", "Saudável"]
        dados_risco = [risco_critico, risco_atencao, risco_baixo]

        labels_prioridade = ["Crítico (Fila)", "Alto (Em Atend.)", "Médio (IA)", "Baixo (Triagem)"]
        dados_prioridade = [
            fila_espera_count,
            active_chats.filter(status='EM_ATENDIMENTO').count(),
            triagem_ia_count,
            0 
        ]
        
    except Exception as e:
        print(f"[ERRO DASHBOARD] {e}") 
        total_backlog, volume_30d, health_score_avg = 0, 0, 0
        fila_espera_count, triagem_ia_count, zumbis_mortos_count = 0, 0, 0
        labels_vol, dados_vol, labels_equipe, dados_carga = [], [], [], []
        labels_risco, dados_risco, labels_prioridade, dados_prioridade = [], [], [], []

    contexto = {
        'sessions': sessions, 
        'tecnicos': list(tecnicos), 
        'clientes': clientes,
        'tags_atendimento': tags_atendimento,
        'mensagens_rapidas_json': mensagens_rapidas_json,
        'total_backlog': total_backlog,
        'volume_30d': volume_30d,
        'health_score_avg': health_score_avg,
        'fila_espera_count': fila_espera_count,
        'triagem_ia_count': triagem_ia_count,
        'zumbis_mortos_count': zumbis_mortos_count,
        'labels_vol': labels_vol,
        'dados_vol': dados_vol,
        'labels_equipe': labels_equipe,
        'dados_carga': dados_carga,
        'labels_prioridade': labels_prioridade,
        'dados_prioridade': dados_prioridade,
        'labels_risco': labels_risco,
        'dados_risco': dados_risco,
    }
    
    return render(request, 'whatsapp_bot/chat_dashboard.html', contexto)

# 🔥 NOVA VIEW PARA O PWA MOBILE
# ==============================================================================
@login_required
def chat_mobile(request):
    # Carrega menos chats inicialmente para garantir velocidade no celular 4G
    sessions = ChatSession.objects.all().order_by('-ultima_interacao')[:50]
 
    # 🔥 WIDGET DE PONTO RÁPIDO (mesma lógica resumida do cockpit, só para "hoje")
    status_ponto, status_ponto_cor = "Fora do expediente", "neutral"
    proximo_label_ponto = "Marcar Entrada"
    try:
        from controle_horas.models import Apontamento
        hoje = timezone.localdate()
        ponto_hoje = Apontamento.objects.filter(
            usuario=request.user, data=hoje, tipo=Apontamento.TIPO_NORMAL
        ).order_by('id').last()
 
        if not ponto_hoje or not ponto_hoje.manha_inicio:
            proximo_label_ponto = "Marcar Entrada"
        elif not ponto_hoje.manha_fim:
            status_ponto, status_ponto_cor = "Trabalhando agora", "active"
            proximo_label_ponto = "Marcar Saída (Almoço)"
        elif not ponto_hoje.tarde_inicio:
            status_ponto, status_ponto_cor = "Em pausa (almoço)", "pause"
            proximo_label_ponto = "Marcar Volta"
        elif not ponto_hoje.tarde_fim:
            status_ponto, status_ponto_cor = "Trabalhando agora", "active"
            proximo_label_ponto = "Marcar Saída"
        else:
            status_ponto, status_ponto_cor = "Expediente encerrado", "done"
            proximo_label_ponto = "Atendimento Especial"
    except Exception as e:
        print(f"[ERRO WIDGET PONTO MOBILE] {e}", flush=True)
 
    contexto = {
        'sessions': sessions,
        'status_ponto': status_ponto,
        'status_ponto_cor': status_ponto_cor,
        'proximo_label_ponto': proximo_label_ponto,
    }
    return render(request, 'whatsapp_bot/chat_mobile.html', contexto)

@login_required
def chat_messages(request, session_id):
    session = get_object_or_404(ChatSession, id=session_id)
    if getattr(session, 'mensagens_nao_lidas', 0) > 0:
        session.mensagens_nao_lidas = 0
        session.save(update_fields=['mensagens_nao_lidas'])
    
    mensagens_query = session.messages.all().order_by('-timestamp')[:50]
    chat_messages = list(mensagens_query)[::-1]
    total_mensagens = session.messages.count()
    
    return render(request, 'whatsapp_bot/includes/messages_list.html', {
        'session': session, 
        'chat_messages': chat_messages,
        'total_mensagens': total_mensagens
    })

# ==============================================================================
# MELHORIA 2: APRESENTAÇÃO AUTOMÁTICA E DESLIGAMENTO DA IA
# ==============================================================================
@login_required
def assumir_atendimento(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        session = get_object_or_404(ChatSession, id=session_id)
        
        session.tecnico_responsavel = request.user
        session.em_atendimento_ia = False
        session.status = 'EM_ATENDIMENTO'
        session.save()
        
        nome_tecnico = (request.user.first_name or request.user.username).title()
        setor = get_setor_tecnico(request.user).title()
        
        msg_boas_vindas = f"Olá, Eu sou o(a) *{nome_tecnico.upper()}* do setor de *{setor.upper()}*, e estou agora responsável pelo seu atendimento."
        
        enviar_msg_whatsapp(session.whatsapp_number, msg_boas_vindas)
        
        Message.objects.create(session=session, sender_type='SISTEMA', text=f"Atendimento assumido por {nome_tecnico.upper()}.")
        Message.objects.create(session=session, sender_type='TECNICO', text=msg_boas_vindas, tecnico=request.user)
        
        return JsonResponse({'status': 'success'})

# ==============================================================================
# MELHORIA 2: ENVIO LIMPO (SEM ASSINATURA FIXA)
# ==============================================================================
# ==============================================================================
# MELHORIA 2: ENVIO LIMPO (SEM ASSINATURA FIXA) E LIBERAÇÃO DE GRUPOS
# ==============================================================================
@login_required
def enviar_mensagem_tecnico(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        texto = request.POST.get('texto')
        is_interno = request.POST.get('is_interno') == 'true'
        reply_to_id = request.POST.get('reply_to_id')
        quoted_text = request.POST.get('quoted_text')
        edit_id = request.POST.get('edit_message_id')
        
        session = get_object_or_404(ChatSession, id=session_id)
        is_group = "@g.us" in session.whatsapp_number
        
        if session.status == 'FINALIZADO':
            sessao_viva = obter_sessao_ativa(session.whatsapp_number, is_group, session.cliente)
            if sessao_viva and sessao_viva.id != session.id:
                session = sessao_viva
        
        destino = obter_destino_seguro(session.whatsapp_number)
        raw_jid = session.whatsapp_number
        
        # TEXTO LIMPO, SEM ASSINATURA
        texto_api = texto 
        texto_db = texto 
        
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

        # EDITAR MENSAGEM
        if edit_id and not is_interno:
            url_update = f"{EVOLUTION_API_URL.rstrip('/')}/chat/updateMessage/{INSTANCE_NAME}"
            
            msg_obj = Message.objects.filter(message_id__icontains=edit_id).first()
            
            jid_alvo = raw_jid
            msg_id_real = edit_id
            if msg_obj and "|" in str(msg_obj.message_id):
                parts = str(msg_obj.message_id).split("|")
                jid_alvo = parts[0]
                msg_id_real = parts[1]

            jids_tentativa = list(set([jid_alvo, raw_jid, destino]))
            
            for jid in jids_tentativa:
                payload = {
                    "number": jid,
                    "messageId": msg_id_real,
                    "text": texto_api,
                    "key": {"id": msg_id_real, "fromMe": True, "remoteJid": jid}
                }
                try:
                    res = requests.post(url_update, json=payload, headers=headers, timeout=5)
                    if res.status_code in [200, 201]: break
                except: pass

            if msg_obj:
                msg_obj.text = texto_db
                msg_obj.is_edited = True
                msg_obj.save()
            
            return JsonResponse({'status': 'sent'})

        # ENVIO NORMAL
        if not is_interno:
            url_send = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendText/{INSTANCE_NAME}"
            payload_send = {"number": destino, "text": texto_api} 
            
            if reply_to_id:
                clean_reply = reply_to_id.split('|')[-1] if '|' in str(reply_to_id) else reply_to_id
                payload_send["quoted"] = {"key": {"id": clean_reply, "fromMe": False, "remoteJid": destino}, "messageId": clean_reply}
            
            try:
                res_send = requests.post(url_send, json=payload_send, headers=headers, timeout=10)
                msg_id_salvar = ""
                if res_send.status_code in [200, 201]:
                    data = res_send.json()
                    real_remote_jid = data.get('key', {}).get('remoteJid') or data.get('remoteJid') or destino
                    real_id = data.get('key', {}).get('id') or data.get('messageId') or data.get('id', '')
                    msg_id_salvar = f"{real_remote_jid}|{real_id}"
                
                msg_salva = Message.objects.create(
                    session=session, 
                    sender_type='TECNICO', 
                    text=texto_db, 
                    tecnico=request.user, 
                    message_id=msg_id_salvar,
                    quoted_message_id=reply_to_id, 
                    quoted_text=quoted_text
                )
                
                if hasattr(msg_salva, 'ack'):
                    msg_salva.ack = 1
                    msg_salva.save()
                    
                # =========================================================
                # GAMIFICAÇÃO: PONTUAR TÉCNICO POR INTERAÇÃO NO CHAT/GRUPO
                # =========================================================
                identificador = session.cliente.razao_social if session.cliente else session.whatsapp_number.split('@')[0]
                
                if is_group:
                    identificador = f"Grupo: {session.push_name or identificador}"
                    acao_gamificacao = 'responder_grupo'
                else:
                    acao_gamificacao = 'atualizar_chamado'
                
                processar_acao_gamificada(
                    usuario=request.user, 
                    acao=acao_gamificacao,
                    detalhe=f"Interação com: {identificador}"
                )
                
            except Exception as e:
                print(f"[ERRO ENVIO] {e}", flush=True)
                
            session.em_atendimento_ia = False
            
            # Se NÃO for grupo, amarra o técnico. Se for grupo, deixa livre para todos.
            if not is_group:
                session.tecnico_responsavel = request.user
                
            if session.status in ['FINALIZADO', 'AVALIACAO_TECNICO', 'AVALIACAO_NPS', 'TRIAGEM', 'PENDENTE']:
                session.status = 'EM_ATENDIMENTO'
        else:
            # 🔥 INTERCEPTADOR ON-DEMAND
            if texto.startswith('[CMD_TRANSCREVER]|'):
                try:
                    msg_id_alvo = texto.split('|')[1]
                    msg_alvo = Message.objects.get(id=msg_id_alvo)
                    host_url = request.build_absolute_uri('/')[:-1]
                    
                    def transcrever_magica(s_id, m_url, tec_user, base_url):
                        import requests, base64
                        from .bot_engine import transcrever_audio_gemini
                        from .models import BotConfig, ChatSession
                        try:
                            # Puxa o áudio do servidor
                            res = requests.get(base_url + m_url, timeout=15)
                            if res.status_code == 200:
                                b64 = base64.b64encode(res.content).decode('utf-8')
                                chave = BotConfig.objects.first().chave_api_gemini
                                txt = transcrever_audio_gemini(chave, b64, "audio/mp3")
                                if txt:
                                    s_obj = ChatSession.objects.get(id=s_id)
                                    Message.objects.create(session=s_obj, sender_type='INTERNO', text=f"✨ *Transcrição:*\n\n\"{txt}\"", tecnico=tec_user)
                        except Exception as e: print(f"Erro: {e}")

                    import threading
                    threading.Thread(target=transcrever_magica, args=(session.id, msg_alvo.media_url, request.user, host_url)).start()
                except: pass
            else:
                Message.objects.create(session=session, sender_type='INTERNO', text=texto, tecnico=request.user)
        
        session.ultima_interacao = timezone.now()
        session.save()
        return JsonResponse({'status': 'sent'})

@login_required
def enviar_arquivo_tecnico(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        arquivo = request.FILES.get('arquivo')
        session = get_object_or_404(ChatSession, id=session_id)
        
        if session.status == 'FINALIZADO':
            sessao_viva = obter_sessao_ativa(session.whatsapp_number, "@g.us" in session.whatsapp_number, session.cliente)
            if sessao_viva and sessao_viva.id != session.id:
                session = sessao_viva
        
        if arquivo:
            try:
                file_bytes = arquivo.read()
                if not file_bytes: 
                    return JsonResponse({'status': 'error', 'msg': 'Arquivo vazio.'}, status=400)

                mimetype = arquivo.content_type.split(';')[0]
                nome_arquivo = arquivo.name or "midia"
                
                if 'video' in mimetype:
                    file_bytes = converter_para_mp4_whatsapp(file_bytes)
                    mimetype = 'video/mp4'
                    if not nome_arquivo.lower().endswith('.mp4'):
                        nome_arquivo += '.mp4'

                b64_conteudo = base64.b64encode(file_bytes).decode('utf-8') 
                b64_full = f"data:{mimetype};base64,{b64_conteudo}"         
                
                destino = obter_destino_seguro(session.whatsapp_number)
                headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
                
                url_fisica = salvar_midia_fisica(b64_full, mimetype, nome_arquivo)
                
                if 'video' in mimetype:
                    host_url = request.build_absolute_uri('/')[:-1] 
                    link_completo = f"{host_url}{url_fisica}"
                    
                    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendMedia/{INSTANCE_NAME}"
                    payload = {
                        "number": destino, 
                        "mediatype": 'video',
                        "mimetype": 'video/mp4',
                        "media": link_completo,
                        "fileName": f"{uuid.uuid4().hex[:8]}.mp4"
                    }
                    texto_banco = "🎥 Vídeo Enviado"
                    
                elif 'audio' in mimetype or 'webm' in mimetype or 'ogg' in mimetype:
                    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendWhatsAppAudio/{INSTANCE_NAME}"
                    payload = {"number": destino, "audio": b64_conteudo} 
                    texto_banco = "🎤 Áudio Enviado"
                    
                else:
                    url = f"{EVOLUTION_API_URL.rstrip('/')}/message/sendMedia/{INSTANCE_NAME}"
                    
                    if 'pdf' in mimetype: tipo = 'document'
                    elif 'image' in mimetype: tipo = 'image'
                    else: tipo = 'document'
                    
                    if '.' not in nome_arquivo:
                        if tipo == 'document': nome_arquivo += '.pdf'
                        elif 'image' in mimetype: nome_arquivo += '.png'
                    
                    payload = {
                        "number": destino, 
                        "mediatype": tipo, 
                        "mimetype": mimetype, 
                        "media": b64_conteudo, 
                        "fileName": nome_arquivo
                    }
                    
                    if tipo == 'image': texto_banco = "📷 Imagem Enviada"
                    else: texto_banco = f"📎 Arquivo: {nome_arquivo}"
                    
                resposta = requests.post(url, json=payload, headers=headers, timeout=120)
                
                msg_id = ""
                if resposta.status_code in [200, 201]: 
                    res_json = resposta.json()
                    real_jid = res_json.get('key', {}).get('remoteJid') or destino
                    real_id = res_json.get('key', {}).get('id', '') or res_json.get('messageId', '')
                    msg_id = f"{real_jid}|{real_id}" if real_id else ""
                
                try:
                    msg_salva = Message.objects.create(session=session, sender_type='TECNICO', text=texto_banco, media_url=url_fisica, message_id=msg_id, tecnico=request.user)
                except:
                    msg_salva = Message.objects.create(session=session, sender_type='TECNICO', text=texto_banco, media_url=url_fisica, tecnico=request.user)
                
                if hasattr(msg_salva, 'ack'):
                    msg_salva.ack = 1
                    msg_salva.save()
                    # =========================================================
                # GAMIFICAÇÃO: PONTUAR TÉCNICO POR ENVIAR ARQUIVO
                # =========================================================
                processar_acao_gamificada(
                    usuario=request.user, 
                    acao='subir_arquivo',
                    detalhe=f"Mídia enviada para: {session.whatsapp_number.split('@')[0]}"
                )

               
                session.ultima_interacao = timezone.now()
                session.save()

                return JsonResponse({'status': 'sent'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)
    return JsonResponse({'status': 'invalid'}, status=405)

@login_required
def deletar_mensagem(request):
    if request.method == "POST":
        try:
            msg_id_bruto = request.POST.get('message_id')
            msg = get_object_or_404(Message, message_id=msg_id_bruto)
            
            jid_alvo = msg.session.whatsapp_number
            msg_id_real = msg_id_bruto
            if "|" in str(msg_id_bruto):
                parts = str(msg_id_bruto).split("|")
                jid_alvo = parts[0]
                msg_id_real = parts[1]

            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            
            payload_delete = {
                "number": jid_alvo.split(':')[0] if ':' in jid_alvo else jid_alvo,
                "id": msg_id_real,       
                "fromMe": True,          
                "remoteJid": jid_alvo    
            }
            
            url = f"{EVOLUTION_API_URL.rstrip('/')}/chat/deleteMessageForEveryone/{INSTANCE_NAME}"
            res = requests.delete(url, json=payload_delete, headers=headers, timeout=10)

            if res.status_code in [200, 201]:
                msg.is_deleted = True
                msg.text = "🚫 Mensagem apagada"
                msg.media_url = None
                msg.save()
            else:
                payload_fallback = payload_delete.copy()
                payload_fallback["key"] = {"id": msg_id_real, "fromMe": True, "remoteJid": jid_alvo}
                res_f = requests.delete(url, json=payload_fallback, headers=headers, timeout=10)
                if res_f.status_code in [200, 201]:
                    msg.is_deleted = True; msg.text = "🚫 Mensagem apagada"; msg.save()

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error'})

@login_required
def editar_mensagem(request):
    return JsonResponse({'status': 'Em breve'})

@login_required
def transferir_atendimento(request):
    if request.method == "POST":
        session = get_object_or_404(ChatSession, id=request.POST.get('session_id'))
        nome = request.user.first_name or request.user.username
        tecnico_id = request.POST.get('tecnico_id')

        if tecnico_id:
            # ── Transferência para um TÉCNICO específico ──
            from django.contrib.auth.models import User
            tecnico = get_object_or_404(User, id=tecnico_id)
            # o setor vai junto com o técnico (o frontend envia o setor dele)
            if request.POST.get('setor'):
                session.setor_atual = request.POST.get('setor')
            session.tecnico_responsavel = tecnico
            session.em_atendimento_ia = False
            session.status = 'EM_ATENDIMENTO'
            session.save()

            nome_tec = tecnico.first_name or tecnico.username
            # aviso interno na conversa
            Message.objects.create(
                session=session, sender_type='SISTEMA',
                text=f"{nome.upper()} transferiu o atendimento para {nome_tec.upper()} ({session.get_setor_atual_display()})."
            )
            # avisa o CLIENTE (igual quando alguém assume/transfere)
            texto_cliente = f"Você foi transferido para o(a) atendente {nome_tec.upper()}, do setor {session.get_setor_atual_display()}. Em breve você será atendido!"
            threading.Thread(target=enviar_msg_whatsapp, args=(session.whatsapp_number, texto_cliente)).start()
        else:
            # ── Transferência para a FILA de um SETOR (comportamento original) ──
            if request.POST.get('setor'):
                session.setor_atual = request.POST.get('setor')
            session.tecnico_responsavel = None
            session.em_atendimento_ia = True
            session.status = 'PENDENTE'
            session.save()
            Message.objects.create(
                session=session, sender_type='SISTEMA',
                text=f"{nome.upper()} transferiu para a fila: {session.get_setor_atual_display()}."
            )
            # avisa o cliente da transferência de setor
            texto_cliente = f"Seu atendimento foi transferido para o setor {session.get_setor_atual_display()}. Aguarde que já vamos te atender!"
            threading.Thread(target=enviar_msg_whatsapp, args=(session.whatsapp_number, texto_cliente)).start()

        return JsonResponse({'status': 'success'})

@login_required
def encerrar_atendimento(request):
    if request.method == "POST":
        session = get_object_or_404(ChatSession, id=request.POST.get('session_id'))
        motivo_recebido = request.POST.get('motivo', 'Não informado')
        
        session.em_atendimento_ia = False
        
        nome = request.user.first_name or request.user.username
        
        motivos_silenciosos = ['duplicad', 'duplicita', 'spam', 'teste', 'erro']
        pular_pesquisa = any(palavra in motivo_recebido.lower() for palavra in motivos_silenciosos)
        
        if pular_pesquisa:
            session.status = 'FINALIZADO'
            session.save()
            Message.objects.create(
                session=session, 
                sender_type='SISTEMA', 
                text=f"Encerrado silenciosamente por {nome.upper()}. Motivo: {motivo_recebido}"
            )
        else:
            session.status = 'AVALIACAO_TECNICO'
            session.save()
            Message.objects.create(
                session=session, 
                sender_type='SISTEMA', 
                text=f"Encerrado por {nome.upper()}. Motivo: {motivo_recebido}"
            )
            
            texto_pesquisa = f"Seu atendimento foi encerrado! De 1 a 5 estrelas, como você avalia o suporte do(a) {nome.upper()}?"
            threading.Thread(target=enviar_msg_whatsapp, args=(session.whatsapp_number, texto_pesquisa)).start()
        
        # =========================================================================
        # MÓDULO DE RECOMPENSAS: CHAMA O MOTOR DE RPG
        # =========================================================================
        identificador = session.cliente.razao_social if session.cliente else session.whatsapp_number.split('@')[0]
        
        processar_acao_gamificada(
            usuario=request.user, 
            acao='Finalizar Chat no WhatsApp',
            detalhe=f"Cliente: {identificador}"
        )
            
        return JsonResponse({'status': 'success'})  
@login_required
def vincular_cliente(request):
    if request.method == "POST":
        try:
            session = ChatSession.objects.get(id=request.POST.get('session_id'))
            cliente = Cliente.objects.get(pk=request.POST.get('cliente_id'))
            session.cliente = cliente
            session.save()
            
            is_group = "@g.us" in session.whatsapp_number
            msg = f"✅ Grupo vinculado ao cliente: {cliente.razao_social}." if is_group else f"✅ Vinculado a {cliente.razao_social}."
            
            if not is_group:
                telefone_limpo = re.sub(r'\D', '', session.whatsapp_number.split('@')[0])
                if 10 <= len(telefone_limpo) <= 13: 
                    if hasattr(cliente, 'telefone') and not cliente.telefone: 
                        cliente.telefone = telefone_limpo
                    elif hasattr(cliente, 'telefone_responsavel') and not cliente.telefone_responsavel: 
                        cliente.telefone_responsavel = telefone_limpo
                    cliente.save()
                    msg = f"✅ Vinculado e telefone atualizado: {cliente.razao_social}."
                    
            Message.objects.create(session=session, sender_type='SISTEMA', text=msg)

            # =========================================================
            # GAMIFICAÇÃO: PONTUAR TÉCNICO POR VINCULAR O CLIENTE
            # =========================================================
            processar_acao_gamificada(
                usuario=request.user, 
                acao='vincular_cliente',
                detalhe=f"Cliente: {cliente.razao_social}"
            )

            return JsonResponse({'status': 'success'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'invalid_method'})

@csrf_exempt
@login_required
def desvincular_cliente(request):
    if request.method == "POST":
        try:
            session = ChatSession.objects.get(id=request.POST.get('session_id'))
            if session.cliente:
                nome_antigo = session.cliente.razao_social
                session.cliente = None
                session.save()
                Message.objects.create(session=session, sender_type='SISTEMA', text=f"❌ Vínculo desfeito com o cliente: {nome_antigo}.")
                return JsonResponse({'status': 'success'})
            return JsonResponse({'status': 'error', 'message': 'Nenhum cliente vinculado a esta sessão.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'invalid_method'})

@login_required
def iniciar_nova_conversa(request):
    if request.method == "POST":
        numero_bruto = request.POST.get('numero', '')
        numero_limpo = re.sub(r'\D', '', numero_bruto)
        if not numero_limpo: return JsonResponse({'status': 'error', 'message': 'Número inválido'})
        
        if len(numero_limpo) == 10 or len(numero_limpo) == 11:
            if not numero_limpo.startswith('55'): numero_limpo = f"55{numero_limpo}"

        remote_jid = f"{numero_limpo}@lid" if len(numero_limpo) >= 14 else f"{numero_limpo}@s.whatsapp.net"
        cliente = buscar_ou_criar_cliente(remote_jid)
        session = obter_sessao_ativa(remote_jid, False, cliente)
        
        # 🔥 A CORREÇÃO DA MICROCIRURGIA ENTRA AQUI 🔥
        # Se a sessão existe mas está aguardando nota (NPS), ela já está "fechada" para a equipe.
        # Então finalizamos ela no banco à força para liberar uma nova aba em branco!
        if session and session.status in ['AVALIACAO_TECNICO', 'AVALIACAO_NPS']:
            session.status = 'FINALIZADO'
            session.save(update_fields=['status'])
            session = None  # Anula a variável para o código cair no 'else' e criar uma nova
        
        if session:
            if getattr(session, 'em_atendimento_ia', False) or session.tecnico_responsavel:
                dono = session.tecnico_responsavel.first_name.upper() if session.tecnico_responsavel else "Fila / IA"
                setor = session.get_setor_atual_display() if hasattr(session, 'get_setor_atual_display') else "Triagem"
                alerta = f"Atenção: Este cliente já está com atendimento ABERTO!\nResponsável: {dono}\nSetor: {setor}"
                return JsonResponse({'status': 'already_open', 'message': alerta})
            else:
                session.tecnico_responsavel = request.user
                session.em_atendimento_ia = False
                session.status = 'EM_ATENDIMENTO'
                session.save()
                return JsonResponse({'status': 'success', 'session_id': session.id})
        else:
            nova_session = ChatSession.objects.create(
                whatsapp_number=remote_jid, cliente=cliente, tecnico_responsavel=request.user, em_atendimento_ia=False, status='EM_ATENDIMENTO')
            return JsonResponse({'status': 'success', 'session_id': nova_session.id})
        
@login_required
def adicionar_tag(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        tag_id = request.POST.get('tag_id')
        session = get_object_or_404(ChatSession, id=session_id)
        session.tags.add(tag_id)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'invalid_method'}, status=405)

@login_required
def historico_conversa(request, session_id):
    session_atual = get_object_or_404(ChatSession, id=session_id)
    is_group = "@g.us" in session_atual.whatsapp_number
    
    if session_atual.cliente:
        sessoes = ChatSession.objects.filter(cliente=session_atual.cliente).prefetch_related('messages', 'tecnico_responsavel').order_by('-data_inicio')
        nome_cliente = session_atual.cliente.razao_social
    else:
        sessoes = ChatSession.objects.filter(whatsapp_number=session_atual.whatsapp_number).prefetch_related('messages', 'tecnico_responsavel').order_by('-data_inicio')
        nome_cliente = session_atual.push_name or session_atual.whatsapp_number

    total_atendimentos = sessoes.count()
    
    # 1. Médias de Avaliação (Apenas se NÃO for grupo)
    media_tecnico = 0
    media_nps = 0
    if not is_group:
        sessoes_com_nota = sessoes.filter(nota_tecnico__isnull=False)
        media_tecnico = sessoes_com_nota.aggregate(Avg('nota_tecnico'))['nota_tecnico__avg'] or 0
        media_nps = sessoes.filter(nota_nps__isnull=False).aggregate(Avg('nota_nps'))['nota_nps__avg'] or 0

    # 2. Scanner Analítico de Mensagens (Mais rápido e preciso)
    dias_pt = {0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'}
    contagem_momentos = {}
    top_senders = {}
    
    # Puxa do banco de forma otimizada só as mensagens do cliente/grupo
    mensagens_cliente = Message.objects.filter(session__in=sessoes, sender_type='CLIENTE').values('timestamp', 'text')
    
    for m in mensagens_cliente:
        if not m['timestamp']: continue
        data_local = timezone.localtime(m['timestamp'])
        dia_nome = dias_pt.get(data_local.weekday(), '')
        
        hora = data_local.hour
        if 6 <= hora < 12: turno = 'Manhã'
        elif 12 <= hora < 18: turno = 'Tarde'
        elif 18 <= hora <= 23: turno = 'Noite'
        else: turno = 'Madrugada'
        
        momento = f"{dia_nome} ({turno})"
        contagem_momentos[momento] = contagem_momentos.get(momento, 0) + 1
        
        # Se for Grupo, caça quem é o membro que mandou a mensagem
        if is_group and m['text']:
            match = re.search(r'👤\s*_(.*?)_:\n', m['text'])
            if match:
                autor = match.group(1).strip()
                top_senders[autor] = top_senders.get(autor, 0) + 1

    # Ordena Padrão de Contato (Top 5)
    momentos_ordenados = sorted(contagem_momentos.items(), key=lambda x: x[1], reverse=True)[:5]
    top_momentos = [{'nome': k, 'qtd': v} for k, v in momentos_ordenados]

    # Ordena Membros do Grupo (Top 4)
    senders_ordenados = sorted(top_senders.items(), key=lambda x: x[1], reverse=True)[:4]
    top_membros = [{'nome': k, 'qtd': v} for k, v in senders_ordenados]

    # 3. Scanner de Motivos de Encerramento Recentes
    mensagens_fim = Message.objects.filter(
        session__in=sessoes, sender_type='SISTEMA', text__icontains='Motivo:'
    ).order_by('-timestamp')[:5]

    motivos_recentes = []
    for m in mensagens_fim:
        try:
            texto = m.text.replace('Encerrado silenciosamente', 'Encerrado')
            partes = texto.split('. Motivo:')
            if len(partes) > 1:
                motivo = partes[1].strip()
                quem = partes[0].replace('Encerrado por ', '').strip()
                motivos_recentes.append({'data': m.timestamp, 'motivo': motivo, 'tecnico': quem})
        except: pass

    # 🔥 4. MAPA DE ASSUNTOS (Nuvem de Palavras) EXCLUSIVO PARA GRUPOS
    top_palavras = []
    if is_group:
        import random
        from collections import Counter
        
        # Filtro SUPER RIGOROSO (Matando os lixos do WhatsApp)
        STOP_WORDS = {'que', 'não', 'nao', 'para', 'com', 'por', 'uma', 'como', 'mais', 'mas', 'foi', 'ele', 'ela', 'aqui', 'isso', 'esse', 'essa', 'tem', 'dos', 'das', 'nos', 'nas', 'está', 'esta', 'estão', 'estao', 'seu', 'sua', 'aos', 'bom', 'dia', 'boa', 'tarde', 'noite', 'vou', 'vai', 'quem', 'já', 'ja', 'bem', 'muito', 'quando', 'onde', 'também', 'tambem', 'então', 'entao', 'assim', 'apenas', 'mesmo', 'você', 'voce', 'tudo', 'fazer', 'dar', 'pode', 'pra', 'pro', 'sobre', 'sem', 'até', 'ate', 'nós', 'porque', 'pq', 'qual', 'são', 'sao', 'ser', 'ter', 'ver', 'vez', 'vamos', 'pelo', 'pela', 'num', 'numa',
        'áudio', 'audio', 'imagem', 'foto', 'vídeo', 'video', 'mensagem', 'enviada', 'enviado', 'certo', 'feito', 'vezes', 'agora', 'preciso', 'precisa', 'vocês', 'eles', 'nesse', 'neste', 'novo', 'algum', 'nada', 'obrigado', 'obrigada', 'valeu', 'beleza', 'okay', 'qualquer', 'coisa', 'agora', 'dando', 'conseguem'}
        
        texto_completo = " ".join([m['text'] for m in mensagens_cliente if m['text']])
        texto_limpo = re.sub(r'👤\s*_(.*?)_:\n', ' ', texto_completo)
        
        palavras_uteis = []
        if nlp:
            # A MÁGICA ACONTECE AQUI: A IA lê o texto e classifica gramaticalmente
            doc = nlp(texto_limpo.lower())
            for token in doc:
                # Se for Substantivo (NOUN) ou Nome Próprio (PROPN), e não for lixo, a gente guarda!
                if token.pos_ in ['NOUN', 'PROPN'] and len(token.text) > 3 and token.text not in STOP_WORDS:
                    palavras_uteis.append(token.text)
        else:
            # Fallback de segurança caso o spaCy não esteja instalado
            palavras = re.findall(r'\b[a-záéíóúãõâêîôûç]+\b', texto_limpo.lower())
            palavras_uteis = [p for p in palavras if p not in STOP_WORDS and len(p) > 3]
        
        # 🔥 REDUZIDO PARA O TOP 20 PALAVRAS MAIS USADAS
        contagem = Counter(palavras_uteis).most_common(20)
        cores_nuvem = ['#38bdf8', '#34d399', '#fbbf24', '#c084fc', '#f472b6', '#a78bfa', '#818cf8', '#2dd4bf', '#ef4444', '#10b981']
        
        if contagem:
            max_count = contagem[0][1]
            min_count = contagem[-1][1]
            for palavra, qtd in contagem:
                if max_count == min_count:
                    size = 1.5
                else:
                    size = 0.7 + ((qtd - min_count) / (max_count - min_count)) * 3.5
                
                top_palavras.append({
                    'texto': palavra,
                    # 🔥 TRANSFORMA EM STRING PARA O DJANGO NÃO COLOCAR VÍRGULA NO CSS:
                    'tamanho': str(round(size, 2)), 
                    'qtd': qtd,
                    'cor': random.choice(cores_nuvem)
                })
        
        random.shuffle(top_palavras)

    contexto = {
        'nome_cliente': nome_cliente,
        'sessoes': sessoes,
        'sessao_atual_id': session_atual.id,
        'total_atendimentos': total_atendimentos,
        'media_tecnico': round(media_tecnico, 1),
        'media_nps': round(media_nps, 1),
        'top_momentos': top_momentos,
        'motivos_recentes': motivos_recentes,
        'is_group': is_group,
        'top_membros': top_membros,
        'top_palavras': top_palavras,
    }
    return render(request, 'whatsapp_bot/historico_completo.html', contexto)

# ==============================================================================
# AGENT ASSIST: SUGESTÃO DE RESPOSTA PARA O TÉCNICO
# ==============================================================================
@login_required
def sugerir_resposta_ia(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        session = get_object_or_404(ChatSession, id=session_id)
        
        from .bot_engine import chamar_gemini_rest
        from .ia_memoria import buscar_artigos_relevantes, obter_historico
        
        config = BotConfig.objects.first()
        if not config or not config.chave_api_gemini:
            return JsonResponse({'status': 'error', 'msg': 'API do Gemini não configurada.'})
        
        # Pega a última mensagem do cliente para buscar na Base de Conhecimento
        ultima_msg = session.messages.filter(sender_type='CLIENTE').order_by('-timestamp').first()
        texto_busca = ultima_msg.text if ultima_msg else ""
        
        historico = obter_historico(session, limite=10)
        base_conhecimento = buscar_artigos_relevantes(texto_busca) if texto_busca else ""
        nome_tec = request.user.first_name or request.user.username
        
        prompt = f"""
        Você é um assistente de IA escrevendo um rascunho de resposta para o técnico humano ({nome_tec.title()}) enviar ao cliente no WhatsApp.
        O setor que o cliente está agora é: {session.get_setor_atual_display()}.
        
        [BASE TÉCNICA (Se aplicável ao problema)]
        {base_conhecimento}
        
        [HISTÓRICO RECENTE DA CONVERSA]
        {historico}
        
        SUA TAREFA:
        Escreva APENAS o texto da resposta que o técnico deve enviar. Seja direto, empático, natural e resolutivo.
        Se a solução estiver na base técnica, explique o passo a passo.
        Se não houver solução óbvia, sugira uma resposta investigativa (ex: pedindo acesso ao AnyDesk ou fotos do erro).
        NÃO escreva introduções como "Aqui está a sugestão:". Devolva SÓ o texto pronto para envio.
        """
        
        sugestao = chamar_gemini_rest(config.chave_api_gemini, prompt)
        
        if sugestao:
            return JsonResponse({'status': 'success', 'sugestao': sugestao.strip()})
        else:
            return JsonResponse({'status': 'error', 'msg': 'Falha ao gerar sugestão. Tente novamente.'})
            
    return JsonResponse({'status': 'invalid_method'}, status=405)

# ==============================================================================
# AGENT ASSIST 2.0: POLIR TEXTO E RESUMO DE PASSAGEM DE BASTÃO
# ==============================================================================
@login_required
def otimizar_texto_ia(request):
    if request.method == "POST":
        texto_original = request.POST.get('texto', '')
        if not texto_original.strip():
            return JsonResponse({'status': 'error', 'msg': 'Digite algo primeiro para otimizar.'})
        
        from .bot_engine import chamar_gemini_rest
        from .models import BotConfig
        
        config = BotConfig.objects.first()
        if not config or not config.chave_api_gemini:
            return JsonResponse({'status': 'error', 'msg': 'API do Gemini não configurada.'})
        
        prompt = f"""
        Você é um assistente de reescrita para um técnico de suporte da empresa Lógica Tecnologia.
        Sua missão é pegar o texto bruto abaixo e reescrevê-lo de forma EXTREMAMENTE POLIDA, profissional, empática e clara (padrão Disney de qualidade).
        
        Regras:
        1. Corrija erros ortográficos e de pontuação.
        2. NÃO adicione saudações ou despedidas ("Olá", "Abraço") se elas não existirem no original, apenas reescreva a ideia central.
        3. Devolva APENAS o texto otimizado, sem aspas e sem introdução.
        
        Texto original: "{texto_original}"
        """
        
        texto_polido = chamar_gemini_rest(config.chave_api_gemini, prompt)
        if texto_polido:
            return JsonResponse({'status': 'success', 'texto_otimizado': texto_polido.strip()})
        return JsonResponse({'status': 'error', 'msg': 'Falha ao processar na IA.'})
    return JsonResponse({'status': 'invalid_method'}, status=405)

@login_required
def resumir_chat_ia(request):
    if request.method == "POST":
        session_id = request.POST.get('session_id')
        session = get_object_or_404(ChatSession, id=session_id)
        
        from .bot_engine import chamar_gemini_rest
        from .models import BotConfig
        
        config = BotConfig.objects.first()
        if not config or not config.chave_api_gemini:
            return JsonResponse({'status': 'error', 'msg': 'API do Gemini não configurada.'})
        
        # 🔥 FILTRA APENAS MENSAGENS TROCADAS HOJE
        hoje = timezone.localtime(timezone.now()).date()
        inicio_dia = timezone.make_aware(timezone.datetime.combine(hoje, timezone.datetime.min.time()))
        
        msgs_hoje = session.messages.filter(timestamp__gte=inicio_dia).exclude(sender_type='SISTEMA').order_by('timestamp')
        
        if not msgs_hoje.exists():
            return JsonResponse({'status': 'error', 'msg': 'Não há mensagens do cliente ou da IA hoje para resumir.'})
            
        historico = "\n".join([f"{m.get_sender_type_display()}: {m.text}" for m in msgs_hoje])
        
        prompt = f"""
        Você está auxiliando um técnico que acaba de assumir um atendimento ou virar o turno.
        Faça um resumo EXTREMAMENTE DIRETO do histórico de mensagens trocadas HOJE.
        
        Regras:
        1. Use no máximo 4 tópicos curtos (bullet points).
        2. Foque EXCLUSIVAMENTE em: qual é o problema relatado e o que já foi tentado/informado pela IA ou técnico.
        3. Não invente nenhuma informação extra.
        4. Retorne apenas os bullet points.
        
        Histórico de hoje:
        {historico}
        """
        
        resumo = chamar_gemini_rest(config.chave_api_gemini, prompt)
        
        if resumo:
            Message.objects.create(
                session=session, 
                sender_type='INTERNO', 
                text=f"📋 *Resumo de Passagem de Bastão (Hoje):*\n\n{resumo.strip()}", 
                tecnico=request.user
            )
            return JsonResponse({'status': 'success'})
            
        return JsonResponse({'status': 'error', 'msg': 'Falha ao processar na IA.'})
    return JsonResponse({'status': 'invalid_method'}, status=405)