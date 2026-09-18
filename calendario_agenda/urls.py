# calendario_agenda/urls.py
from django.urls import path
from . import views

app_name = "calendario_agenda"

urlpatterns = [
    path("", views.calendar_home, name="calendar"),
    path("novo/", views.event_create, name="event_create"),
    path("<int:pk>/editar/", views.event_edit, name="event_edit"),
    path("<int:pk>/excluir/", views.event_delete, name="event_delete"),
    path("confirmar/<uuid:token>/<str:decision>/", views.confirm_attendance, name="confirm_attendance"),
    path('evento/<int:pk>/atualizar-data/', views.atualizar_data_evento, name='atualizar_data_evento'),
]
