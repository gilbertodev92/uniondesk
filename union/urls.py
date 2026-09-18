from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView  # 🔥 Adicionado para ler o HTML direto

urlpatterns = [
    path('admin/', admin.site.urls),
    path("select2/", include("django_select2.urls")),
    #path('', include('users.urls')),
    path('usuarios/', include('users.urls')),
    path('whatsapp-bot/', include('whatsapp_bot.urls')),
    path("atendimentos/", include("atendimentos_chamados.urls")),
    path('clientes/', include('clientes_sistemas.urls')),
    path('base-conhecimento/', include('base_conhecimento.urls', namespace='base_conhecimento')),
    path("cofre/", include("cofre_senhas.urls")),  
    path("arquivos/", include("arquivos_instaladores.urls", namespace="arquivos_instaladores")),
    path("implantacoes/", include("implantacao.urls")),
    path("cs/", include("cs_satisfacao.urls")),
    path('sistemas/', include('sistemas.urls')),
    path('controle-horas/', include(('controle_horas.urls', 'controle_horas'), namespace='controle_horas')),
    path('accounts/', include('django.contrib.auth.urls')),  
    path('calendario-agenda/', include('calendario_agenda.urls', namespace='calendario_agenda')),
    path('ckeditor/', include('ckeditor_uploader.urls')),
    path('relatorios/', include('central_relatorios.urls')),
    path('recompensas/', include('recompensas.urls')), 
    path('comercial/', include('crm_vendas.urls')),
    path('setup/', include('setup.urls')),  # Movemos o setup pra desocupar a raiz
    path("assistente/", include("assistente_ia.urls")),    
    # 🔥 AQUI ESTÁ A MÁGICA: A Rota Raiz agora carrega o seu site direto!
    path('', TemplateView.as_view(template_name='union.html'), name='site_publico'),
    path("raio-x/", include("raio_x.urls")),
]

# Anexos de chamados: servidos tambem com DEBUG=False.
from django.views.static import serve as _serve
from django.urls import re_path as _re_path

urlpatterns += [
    _re_path(r'^media/(?P<path>.*)$', _serve, {'document_root': settings.MEDIA_ROOT}),
]
