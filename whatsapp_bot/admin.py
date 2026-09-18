from django.contrib import admin
from .models import ChatSession, Message, TagAtendimento, MensagemRapida, BotConfig

@admin.register(TagAtendimento)
class TagAtendimentoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'cor')
    search_fields = ('nome',)
    list_per_page = 20

@admin.register(BotConfig)
class BotConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'chave_api_gemini_oculta', 'modelo_ia')

    fieldsets = (
        ("Conexão", {
            "fields": ("chave_api_gemini", "modelo_ia"),
        }),
        ("Horário de Atendimento", {
            "fields": ("horario_inicio_semana", "horario_fim_semana",
                       "horario_inicio_sabado", "horario_fim_sabado"),
        }),
        ("Personalidade da IA", {
            "fields": ("prompt_ia_triagem", "prompt_analista_digital"),
            "description": "Quem a IA é em cada cenário. Deixe vazio para usar o padrão.",
        }),
        ("Conhecimento e Regras", {
            "fields": ("identidade_empresa", "regras_negocio", "instrucoes_suporte_24h"),
        }),
        ("Mensagens Automáticas", {
            "fields": ("mensagem_saudacao", "mensagem_fora_horario"),
        }),
        ("Voz (áudio)", {
            "fields": ("modelo_tts", "voz_tts"),
        }),
    )

    def chave_api_gemini_oculta(self, obj):
        if obj.chave_api_gemini:
            return f"{obj.chave_api_gemini[:8]}********"
        return "Não configurada"
    chave_api_gemini_oculta.short_description = 'API Key'

@admin.register(MensagemRapida)
class MensagemRapidaAdmin(admin.ModelAdmin):
    list_display = ('atalho', 'titulo', 'texto_preview')
    search_fields = ('atalho', 'titulo', 'texto')

    def texto_preview(self, obj):
        return obj.texto[:50] + '...' if len(obj.texto) > 50 else obj.texto
    texto_preview.short_description = 'Pré-visualização'

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('whatsapp_number', 'push_name', 'cliente', 'tecnico_responsavel', 'status', 'setor_atual', 'em_atendimento_ia')
    list_filter = ('status', 'setor_atual', 'em_atendimento_ia')
    search_fields = ('whatsapp_number', 'push_name')
    raw_id_fields = ('cliente', 'tecnico_responsavel')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'sender_type', 'timestamp', 'tecnico')
    list_filter = ('sender_type', 'timestamp')
    search_fields = ('text',)

