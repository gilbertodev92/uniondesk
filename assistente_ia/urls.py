from django.urls import path

from . import views

app_name = "assistente_ia"

urlpatterns = [
    path("perguntar/", views.assistente_perguntar, name="perguntar"),
    path("relatorio/", views.relatorio_uso, name="relatorio_uso"),
    path("tela/", views.tela_cheia, name="tela_cheia"),
]