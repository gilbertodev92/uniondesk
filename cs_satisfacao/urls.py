from django.urls import path
from . import views

app_name = 'cs_satisfacao'

urlpatterns = [
    # Painel Principal
    path('', views.painel_cs, name='painel_cs'),
    
    # Criar novo evento (Tela e Modal)
    path('novo/', views.criar_cs, name='criar_cs'),
    path('cliente/<int:cliente_id>/adicionar-evento/', views.adicionar_evento_cliente, name='adicionar_evento_cliente'),
    path('evento/<int:evento_id>/concluir/', views.concluir_evento_cs, name='concluir_evento_cs'),
    # Detalhes do Cliente
    path('cliente/<int:cliente_id>/', views.detalhe_cliente, name='detalhe_cliente'),
    
    # API de Busca (Para o Autocomplete funcionar)
    path('api/clientes/', views.buscar_clientes, name='buscar_clientes'),
    
    # Rota do nosso novo botão de Cancelamento (Churn)
    path('cancelar-cliente/', views.cancelar_cliente, name='cancelar_cliente'),
]