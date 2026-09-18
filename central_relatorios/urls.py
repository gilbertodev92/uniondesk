from django.urls import path
from . import views

app_name = 'central_relatorios'

urlpatterns = [
    path('', views.central_home, name='central_home'),
]