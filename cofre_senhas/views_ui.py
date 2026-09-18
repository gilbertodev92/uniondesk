# cofre_senhas/views_ui.py
import json
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST

from .decorators import (
    vault_required,
    unlock_vault_session,
    lock_vault_session,
)

# ⚠️ CORREÇÃO DE SEGURANÇA
# O antigo unlock_view_password buscava Credential.objects.get(pk=pk) direto,
# sem checar dono nem setor: qualquer usuário autenticado lia a senha de
# qualquer credencial só trocando o número na URL (IDOR).
# Agora TODA busca passa pelo motor de setor.
from .models import Credential, CredentialAccount
from .views import get_credenciais_do_setor, _log_action


# ── Rate limiting do PIN ────────────────────────────────────────────
# Antes: PIN global de 6 dígitos, csrf_exempt, tentativas infinitas.
PIN_MAX_TENTATIVAS = getattr(settings, "COFRE_PIN_MAX_TENTATIVAS", 5)
PIN_BLOQUEIO_SEGUNDOS = getattr(settings, "COFRE_PIN_BLOQUEIO_SEGUNDOS", 300)

_PIN_FAILS_KEY = "cofre_pin_fails"
_PIN_LOCKED_UNTIL_KEY = "cofre_pin_locked_until"


def _pin_bloqueado_por(request) -> int:
    """Segundos restantes de bloqueio, ou 0."""
    until = request.session.get(_PIN_LOCKED_UNTIL_KEY, 0)
    restante = int(until - time.time())
    return max(restante, 0)


def _registra_falha_pin(request):
    fails = request.session.get(_PIN_FAILS_KEY, 0) + 1
    request.session[_PIN_FAILS_KEY] = fails
    if fails >= PIN_MAX_TENTATIVAS:
        request.session[_PIN_LOCKED_UNTIL_KEY] = time.time() + PIN_BLOQUEIO_SEGUNDOS
        request.session[_PIN_FAILS_KEY] = 0
    request.session.modified = True


def _limpa_falhas_pin(request):
    request.session.pop(_PIN_FAILS_KEY, None)
    request.session.pop(_PIN_LOCKED_UNTIL_KEY, None)
    request.session.modified = True


@login_required
def vault_page(request):
    return render(request, "cofre_senhas/vault.html")


@login_required
@require_POST
def unlock_pin(request):
    """
    POST {pin} -> destrava a sessão do cofre.

    Mudanças:
      - @csrf_exempt REMOVIDO (o front já manda X-CSRFToken).
      - rate limit por sessão.
      - não devolve mais a lista de credenciais no corpo da resposta.
    """
    bloqueado = _pin_bloqueado_por(request)
    if bloqueado:
        return JsonResponse(
            {"error": "locked", "retry_in": bloqueado},
            status=429,
        )

    pin = None
    if request.body:
        try:
            pin = json.loads(request.body.decode("utf-8")).get("pin")
        except Exception:
            pin = None
    if not pin:
        pin = request.POST.get("pin")

    vault_pin = getattr(settings, "COFRE_VAULT_PIN", None)
    if not vault_pin:
        return HttpResponseForbidden()

    # comparação em tempo constante evita timing attack
    from hmac import compare_digest
    if not pin or not compare_digest(str(pin), str(vault_pin)):
        _registra_falha_pin(request)
        restante = _pin_bloqueado_por(request)
        if restante:
            return JsonResponse({"error": "locked", "retry_in": restante}, status=429)
        return HttpResponseForbidden()

    _limpa_falhas_pin(request)
    unlock_vault_session(request)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def lock_vault(request):
    lock_vault_session(request)
    return JsonResponse({"ok": True})


@login_required
@vault_required
@require_POST
def unlock_view_password(request, pk):
    """
    Revela a senha de UMA credencial.

    Antes: sem PIN, sem dono, via GET. Agora: exige cofre destravado,
    passa pelo motor de setor, é POST (não fica no histórico/log do
    servidor) e grava auditoria.
    """
    cred = get_object_or_404(get_credenciais_do_setor(request.user), pk=pk)
    cred.touch_access()
    _log_action(request, cred.id, "VIEW", details=f"Revelou senha de {cred.title}")
    return JsonResponse({"password": cred.get_password()})


@login_required
@vault_required
@require_POST
def unlock_account_password(request, pk):
    """
    Revela a senha de UM acesso individual (CredentialAccount).

    É isso que permite revelar 1 cliente por vez em vez de despejar
    todos de uma vez, e auditar exatamente qual foi revelado.
    """
    account = get_object_or_404(
        CredentialAccount.objects.filter(
            credential__in=get_credenciais_do_setor(request.user)
        ),
        pk=pk,
    )
    account.touch_access()
    _log_action(
        request,
        account.credential_id,
        "VIEW",
        details=f"Revelou acesso '{account.label}' de {account.credential.title}",
    )
    return JsonResponse({"password": account.get_password()})


@login_required
@vault_required
@require_POST
def unlock_log(request, pk):
    _log_action(request, pk, "VIEW", details="Cópia para a área de transferência")
    return JsonResponse({"ok": True})