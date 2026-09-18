from django.urls import path
from django.shortcuts import render

app_name = "implantacao"

def listar_implantacoes(request):
    return render(request, "implantacao/listar.html")

urlpatterns = [
    path("", listar_implantacoes, name="listar"),
]
