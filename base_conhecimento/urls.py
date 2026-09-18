# /base_conhecimento/urls.py
from django.urls import path
from . import views

app_name = "base_conhecimento"

urlpatterns = [
    path("", views.rom_base_conhecimento, name="rom"),

    # Busca em TODOS os sistemas. Fica antes das rotas de <sistema_id>
    # para não ser capturada por elas.
    path("buscar/", views.busca_global, name="busca_global"),

    path("sistema/<str:sistema_id>/", views.sistema_base_conhecimento, name="sistema"),
    path("sistema/<str:sistema_id>/novo/", views.artigo_create, name="artigo_create"),
    path(
        "sistema/<str:sistema_id>/artigo/<slug:slug>/",
        views.artigo_detalhe,
        name="artigo_detalhe",
    ),
    path("sistema/<str:sistema_id>/artigo/<slug:slug>/pdf/", views.artigo_pdf, name="artigo_pdf"),
    path("sistema/<str:sistema_id>/artigo/<slug:slug>/editar/", views.artigo_edit, name="artigo_edit"),
]