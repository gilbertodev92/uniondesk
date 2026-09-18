from django.urls import path
from . import views
from . import views_ui

app_name = "cofre_senhas"

urlpatterns = [
    # Página principal (tela de PIN)
    path("", views_ui.vault_page, name="index"),

    # Lista de credenciais
    path("list/", views.list_credentials, name="list"),

    # CRUD
    path("create/", views.create_credential, name="create"),
    path("edit/<int:pk>/", views.edit_credential, name="edit"),
    path("view/<int:pk>/", views.view_credential_plain, name="view_plain"),

    # Unlock system
    path("unlock/", views_ui.unlock_pin, name="unlock_pin"),
    path("unlock/lock/", views_ui.lock_vault, name="lock_vault"),
    path("unlock/view/<int:pk>/", views_ui.unlock_view_password, name="unlock_view_password"),

    # NOVO: revela a senha de UM acesso individual (um cliente por vez)
    path("unlock/account/<int:pk>/", views_ui.unlock_account_password, name="unlock_account_password"),

    path("unlock/log/<int:pk>/", views_ui.unlock_log, name="unlock_log"),
]