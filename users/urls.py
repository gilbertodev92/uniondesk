# users/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('painel-usuarios/', views.painel_usuarios, name='painel_usuarios'),

    # Usuários
    path('usuarios/novo/', views.usuario_create, name='usuario_create'),
    path('usuarios/<int:pk>/editar/', views.usuario_edit, name='usuario_edit'),

    # Grupos
    path('grupos/novo/', views.grupo_create, name='grupo_create'),
    path('grupos/<int:pk>/editar/', views.grupo_edit, name='grupo_edit'),
    path('grupos/', views.painel_grupos, name='painel_grupos'),

    # Login/Logout (caso ainda não estejam)
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
     path('logout/', views.user_logout, name='user_logout'), 
     path('relatorio-cidade/', views.relatorio_cidade, name='relatorio_cidade'),

    path('', views.home, name='home'),  # essa linha define a URL home

    path('relatorio-cidade-excel/', views.relatorio_cidade_excel, name='relatorio_cidade_excel'),
    path('relatorio-sistema/', views.relatorio_sistema, name='relatorio_sistema'),
    path('relatorio-sistema-excel/', views.relatorio_sistema_excel, name='relatorio_sistema_excel'),
]
