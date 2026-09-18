from django.urls import path
from . import views

app_name = 'recompensas'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Check-in diário
    path('resgate-diario/', views.resgate_diario, name='resgate_diario'),

    # Roleta (nome antigo mantido por compatibilidade)
    path('girar-tigrinho/', views.girar_tigrinho, name='girar_tigrinho'),

    # Pó mágico
    path('desencantar/', views.desencantar, name='desencantar'),
    path('craftar/', views.craftar, name='craftar'),
    path('montar/', views.montar, name='montar'),

    # Loja oficial (nome antigo mantido)
    path('resgatar-item/<int:item_id>/', views.resgatar_item, name='resgatar_item'),

    # Missões (nome antigo mantido)
    path('resgatar-missao/', views.resgatar_missao, name='resgatar_missao'),

    # Mercado clandestino
    path('mercado/anunciar/', views.criar_anuncio, name='criar_anuncio'),
    path('mercado/comprar/<int:anuncio_id>/', views.comprar_anuncio, name='comprar_anuncio'),
    path('mercado/cancelar/<int:anuncio_id>/', views.cancelar_anuncio, name='cancelar_anuncio'),
]