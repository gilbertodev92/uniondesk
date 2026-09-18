from django.urls import path
from . import views

urlpatterns = [
    path('', views.painel_sistemas, name='painel_sistemas'),
    path('novo/', views.sistema_create, name='sistema_create'),
    path('<int:pk>/editar/', views.sistema_edit, name='sistema_edit'),
]