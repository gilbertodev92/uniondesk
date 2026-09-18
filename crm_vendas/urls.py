from django.urls import path
from . import views

app_name = 'crm_vendas'

urlpatterns = [
    path('', views.kanban_vendas, name='kanban'), 
    path('prospeccoes/', views.lista_prospeccoes, name='lista_prospeccoes'),
    path('perdidos/', views.lista_perdidos, name='lista_perdidos'),
    path('ganhos/', views.lista_ganhos, name='lista_ganhos'), 
    
    path('atualizar-etapa/', views.atualizar_etapa_lead, name='atualizar_etapa_lead'),
    path('novo-lead-ajax/', views.lead_create_ajax, name='lead_create_ajax'),
    path('importar-csv/', views.importar_leads_csv, name='importar_leads_csv'),
    
    path('api/lead/<str:lead_id>/assumir/', views.assumir_prospeccao_ajax, name='assumir_prospeccao_ajax'),
    path('api/lead/<str:lead_id>/descartar/', views.descartar_prospeccao_ajax, name='descartar_prospeccao_ajax'),
    path('api/lead/<str:lead_id>/obs-rapida/', views.salvar_obs_prospeccao_ajax, name='salvar_obs_prospeccao_ajax'),
    path('api/lead/<str:lead_id>/prorrogar-sla/', views.prorrogar_sla_lead, name='prorrogar_sla_lead'), # NOVA: Prorrogação
    
    path('api/lead/<str:lead_id>/', views.get_lead_details, name='get_lead_details'),
    path('api/lead/<str:lead_id>/nota/', views.add_lead_note, name='add_lead_note'),
    path('api/lead/<str:lead_id>/fechar/', views.fechar_lead, name='fechar_lead'),
    path('api/lead/<str:lead_id>/edit/', views.editar_lead_ajax, name='editar_lead_ajax'),
    path('api/lead/<str:lead_id>/arquivo/', views.upload_arquivo_lead, name='upload_arquivo_lead'),
    path('lead/<str:lead_id>/proposta/', views.imprimir_proposta, name='imprimir_proposta'),
    
    path('minhas-vendas/', views.minhas_vendas, name='minhas_vendas'),
    path('minhas-vendas/excluir/<int:venda_id>/', views.excluir_venda, name='excluir_venda'),
    # Adicione junto das outras rotas API
    path('api/prospeccao/<str:prospeccao_id>/', views.get_prospeccao_details, name='get_prospeccao_details'),
    path('api/prospeccao/<str:prospeccao_id>/edit/', views.editar_prospeccao_ajax, name='editar_prospeccao_ajax'),
    path('prospeccoes-descartadas/', views.lista_descartadas, name='lista_descartadas'),
    path('gestor/', views.dashboard_gestor, name='dashboard_gestor'),
    
]