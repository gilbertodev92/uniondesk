from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from .decorators import vault_required
from .forms import CredentialForm, CredentialAccountFormSet
from .models import Credential
from .models_audit import PasswordAccessLog


def _log_action(request, credential_id, action, details=None):
    ip = request.META.get("REMOTE_ADDR")
    ua = request.META.get("HTTP_USER_AGENT", "")[:512]
    PasswordAccessLog.objects.create(
        credential_id=credential_id,
        user=request.user if request.user.is_authenticated else None,
        action=action,
        ip_address=ip,
        user_agent=ua,
        details=details[:200] if details else None,
    )


# 🔥 MOTOR DE COMPARTILHAMENTO DE SETOR (Escudo de Segurança)
def get_credenciais_do_setor(user):
    if user.is_superuser:
        return Credential.objects.all()

    grupos_do_usuario = user.groups.all()
    if grupos_do_usuario.exists():
        # senhas que EU criei OU criadas por alguém do meu setor
        return Credential.objects.filter(
            Q(owner=user) | Q(owner__groups__in=grupos_do_usuario)
        ).distinct()

    return Credential.objects.filter(owner=user)


@login_required
@vault_required
def list_credentials(request):
    qs = (
        get_credenciais_do_setor(request.user)
        .annotate(n_accounts=Count("accounts"))
        .order_by("-is_favorite", "-updated_at")
    )
    return render(request, "cofre_senhas/list.html", {"credentials": qs})


@login_required
@vault_required
def create_credential(request):
    if request.method == "POST":
        form = CredentialForm(request.POST)
        if form.is_valid():
            cred = form.save(owner=request.user)
            formset = CredentialAccountFormSet(request.POST, instance=cred)
            if formset.is_valid():
                formset.save()
                _log_action(request, cred.id, "CREATE", details=f"Criou {cred.title}")
                messages.success(request, "Credencial salva e criptografada.")
                return redirect(reverse("cofre_senhas:list"))
            cred.delete()  # não deixa credencial órfã se os acessos falharem
        else:
            formset = CredentialAccountFormSet(request.POST)
    else:
        form = CredentialForm()
        formset = CredentialAccountFormSet()

    return render(request, "cofre_senhas/form.html", {
        "form": form,
        "formset": formset,
        "creating": True,
    })


@login_required
@vault_required
def edit_credential(request, pk):
    cred = get_object_or_404(get_credenciais_do_setor(request.user), pk=pk)

    if request.method == "POST":
        form = CredentialForm(request.POST, instance=cred)
        formset = CredentialAccountFormSet(request.POST, instance=cred)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            _log_action(request, cred.id, "UPDATE", details=f"Atualizou {cred.title}")
            messages.success(request, "Credencial atualizada.")
            return redirect(reverse("cofre_senhas:list"))
    else:
        form = CredentialForm(instance=cred)
        formset = CredentialAccountFormSet(instance=cred)

    return render(request, "cofre_senhas/form.html", {
        "form": form,
        "formset": formset,
        "creating": False,
        "credential": cred,
    })


@login_required
@vault_required
def view_credential_plain(request, pk):
    """
    Página de consulta da credencial.

    ⚠️ MUDANÇA IMPORTANTE: a senha NÃO é mais renderizada no HTML.
    Antes ela vinha no template e era injetada em atributos onclick
    (quebrava com aspas e ficava no DOM/cache do navegador). Agora o
    HTML só lista os acessos; cada senha é buscada sob demanda, uma
    por vez, via POST autenticado — e cada revelação vira log.
    """
    cred = get_object_or_404(
        get_credenciais_do_setor(request.user).prefetch_related("accounts"),
        pk=pk,
    )
    _log_action(request, cred.id, "VIEW", details=f"Abriu {cred.title}")

    return render(request, "cofre_senhas/view.html", {
        "credential": cred,
        "accounts": cred.accounts.all(),
        "notes": cred.get_notes(),
    })