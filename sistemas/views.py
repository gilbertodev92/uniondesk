from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Sistema
from .forms import SistemaForm

# Permissão customizada
def pode_gerenciar_sistemas(user):
    return user.is_superuser or user.has_perm('users.change_user')

@login_required
@user_passes_test(pode_gerenciar_sistemas)
def painel_sistemas(request):
    sistemas = Sistema.objects.all()
    return render(request, 'sistemas/painel_sistemas.html', {'sistemas': sistemas})

@login_required
@user_passes_test(pode_gerenciar_sistemas)
def sistema_create(request):
    if request.method == 'POST':
        form = SistemaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('painel_sistemas')
    else:
        form = SistemaForm()
    return render(request, 'sistemas/sistema_form.html', {'form': form})

@login_required
@user_passes_test(pode_gerenciar_sistemas)
def sistema_edit(request, pk):
    sistema = get_object_or_404(Sistema, pk=pk)
    if request.method == 'POST':
        form = SistemaForm(request.POST, instance=sistema)
        if form.is_valid():
            form.save()
            return redirect('painel_sistemas')
    else:
        form = SistemaForm(instance=sistema)
    return render(request, 'sistemas/sistema_form.html', {'form': form})
