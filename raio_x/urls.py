from django.urls import path
from . import views

app_name = 'raio_x'

urlpatterns = [
    path('auth/', views.auth_godmode, name='auth'),
    path('dashboard/', views.dashboard_godmode, name='dashboard'),
    path('usuario/<int:user_id>/', views.detalhe_usuario_godmode, name='detalhe_usuario'),
]