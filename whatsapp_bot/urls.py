from django.urls import path
from . import views

app_name = 'whatsapp_bot'

urlpatterns = [
    path('', views.home, name='whatsapp_home'),
    path('webhook/', views.whatsapp_webhook, name='webhook'),
    path('chat/', views.chat_dashboard, name='chat_dashboard'),
    path('chat/cel/', views.chat_mobile, name='chat_mobile'),
    path('chat/<int:session_id>/', views.chat_messages, name='chat_messages'),
    path('enviar/', views.enviar_mensagem_tecnico, name='enviar_mensagem'),
    path('sugerir-resposta/', views.sugerir_resposta_ia, name='sugerir_resposta_ia'), # 🔥 ROTA DA VARINHA MÁGICA
    path('otimizar-texto/', views.otimizar_texto_ia, name='otimizar_texto_ia'),
    path('resumir-chat/', views.resumir_chat_ia, name='resumir_chat_ia'),
    path('enviar-arquivo/', views.enviar_arquivo_tecnico, name='enviar_arquivo'),
    path('transferir/', views.transferir_atendimento, name='transferir'),
    path('adicionar-tag/', views.adicionar_tag, name='adicionar_tag'),
    path('encerrar/', views.encerrar_atendimento, name='encerrar_atendimento'),
    path('nova-conversa/', views.iniciar_nova_conversa, name='iniciar_nova_conversa'),
    path('iniciar/', views.iniciar_nova_conversa, name='iniciar_nova_conversa'),
    path('vincular-cliente/', views.vincular_cliente, name='vincular_cliente'),
    path('assumir/', views.assumir_atendimento, name='assumir_atendimento'),
    path('historico/<int:session_id>/', views.historico_conversa, name='historico_conversa'),
    path('desvincular_cliente/', views.desvincular_cliente, name='desvincular_cliente'),
    
    # ROTAS DE EDIÇÃO E EXCLUSÃO DE MENSAGENS
    path('deletar-mensagem/', views.deletar_mensagem, name='deletar_mensagem'),
    path('editar-mensagem/', views.editar_mensagem, name='editar_mensagem'),
]