from django.urls import path
from . import views

urlpatterns = [
    path("", views.painel_clientes, name="painel_clientes"),
    path("novo/", views.cliente_create, name="cliente_create"),
    path("editar/<int:pk>/", views.cliente_edit, name="cliente_edit"),
    path("buscar-cnpj/", views.buscar_cnpj, name="buscar_cnpj"),
    path("toggle-financeiro/<int:pk>/", views.toggle_status_financeiro, name="toggle_financeiro"),
]
