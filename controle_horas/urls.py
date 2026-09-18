from django.urls import path
from . import views

app_name = "controle_horas"

urlpatterns = [
    # O COCKPIT ÚNICO (Substitui painel, meus, aprovacoes e fechamentos)
    path("painel/", views.cockpit_horas, name="painel"),

    # BATER PONTO (Gatilho Rápido)
    path("bater-agora/", views.bater_ponto_rapido, name="bater_ponto_rapido"),

    # BATER PONTO DE ATUALIZAÇÃO (fora do horário comercial, vinculado a um cliente)
    path("bater-atualizacao/", views.bater_ponto_atualizacao, name="bater_ponto_atualizacao"),

    # AÇÕES DE CRUD MANUAIS (Ocultas na interface, chamadas por modais)
    path("novo/", views.apontamento_create, name="apontamento_create"),
    path("<int:pk>/editar/", views.apontamento_edit, name="apontamento_edit"),
    path("<int:pk>/deletar/", views.apontamento_delete, name="apontamento_delete"),

    # AÇÕES DO GESTOR (Aprovação/Reprovação com 1 clique)
    path("gestao/aprovar/<int:pk>/", views.apontamento_aprovar, name="apontamento_aprovar"),
    path("gestao/reprovar/<int:pk>/", views.apontamento_reprovar, name="apontamento_reprovar"),

    path('api/eventos/', views.api_eventos_agenda, name='api_eventos_agenda'),
    path('api/meu-status-ponto/', views.api_meu_status_ponto, name='api_meu_status_ponto'),
    path('api/eventos/salvar/', views.salvar_evento_agenda, name='salvar_evento_agenda'),
    path('api/eventos/remover/', views.remover_evento_agenda, name='remover_evento_agenda'),

    # RELATÓRIOS E EXPORTAÇÕES
    path("gestao/export/csv/<int:ano>/<int:mes>/", views.export_csv_mes, name="export_csv_mes"),
    path("gestao/espelho/", views.relatorio_espelho_mes_pdf, name="relatorio_espelho_mes_pdf"),
    path("gestao/export/pdf/<int:ano>/<int:mes>/", views.export_relatorio_mes_pdf, name="export_relatorio_mes_pdf"),
    path("gestao/espelho/<int:user_id>/", views.relatorio_espelho_individual_pdf, name="relatorio_espelho_individual_pdf"),

]
