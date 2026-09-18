from django.urls import path
from . import views

app_name = "arquivos_instaladores"

urlpatterns = [
    path("", views.painel_listagem, name="painel"),
    path("novo/", views.item_create, name="create"),
    path("<int:pk>/editar/", views.item_edit, name="edit"),
    path("<int:pk>/excluir/", views.item_delete, name="delete"),
    path("<int:pk>/restaurar/", views.item_restaurar, name="restaurar"),
    path("<int:pk>/download/", views.item_download, name="download"),

    # upload em pedaços
    path("upload/chunk/", views.upload_chunk, name="upload_chunk"),
    path("upload/finalizar/", views.finalizar_upload, name="finalizar_upload"),
]