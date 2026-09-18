from django.urls import path
from . import views

app_name = 'setup'

urlpatterns = [
    # A rota raiz chama a view home
    path('', views.home, name='home'),
]