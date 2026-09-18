from django.urls import path
from . import views

app_name = "atendimentos_chamados"

urlpatterns = [
    path("", views.listar_atendimentos, name="listar"),
    path("novo/", views.criar_atendimento, name="criar"),
    path("<int:numero>/", views.detalhe_atendimento, name="detalhe"),
    path("<int:numero>/enviar/", views.enviar_para_setor, name="enviar"),
    path("<int:numero>/transferir/", views.transferir_atendimento, name="transferir"),
    path("autocomplete-cliente/", views.autocomplete_cliente, name="autocomplete_cliente"),
    path("setor/<int:setor_id>/tecnicos/", views.tecnicos_do_setor, name="tecnicos_do_setor"),
    path("atendimento/<int:numero>/pdf/", views.resumo_implantacao_pdf, name="resumo_implantacao_pdf"),
]