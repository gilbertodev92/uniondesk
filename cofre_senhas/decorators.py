# cofre_senhas/decorators.py
"""
O PIN do cofre era decorativo: a sessão era marcada no unlock e nunca
conferida por ninguém. Dava para ir direto em /cofre/list/ sem PIN.

Este módulo centraliza a checagem. Toda rota que exponha credenciais
deve usar @vault_required.
"""
import time
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

VAULT_SESSION_KEY = "cofre_unlocked"
VAULT_SESSION_AT_KEY = "cofre_unlocked_at"

# Tempo que o cofre permanece destravado (segundos). Ajuste em settings.
VAULT_TIMEOUT_SECONDS = getattr(settings, "COFRE_TIMEOUT_SECONDS", 300)


def vault_is_unlocked(request) -> bool:
    if not request.session.get(VAULT_SESSION_KEY):
        return False

    unlocked_at = request.session.get(VAULT_SESSION_AT_KEY)
    if not unlocked_at:
        return False

    # expira sozinho — antes ficava destravado até o logout
    if (time.time() - float(unlocked_at)) > VAULT_TIMEOUT_SECONDS:
        lock_vault_session(request)
        return False

    return True


def unlock_vault_session(request):
    request.session[VAULT_SESSION_KEY] = True
    request.session[VAULT_SESSION_AT_KEY] = time.time()
    request.session.modified = True


def lock_vault_session(request):
    request.session.pop(VAULT_SESSION_KEY, None)
    request.session.pop(VAULT_SESSION_AT_KEY, None)
    request.session.modified = True


def touch_vault_session(request):
    """Renova a janela a cada uso legítimo do cofre."""
    if request.session.get(VAULT_SESSION_KEY):
        request.session[VAULT_SESSION_AT_KEY] = time.time()
        request.session.modified = True


def vault_required(view_func):
    """Exige cofre destravado. Em AJAX devolve 403 JSON, senão redireciona."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not vault_is_unlocked(request):
            is_ajax = (
                request.headers.get("x-requested-with") == "XMLHttpRequest"
                or request.headers.get("accept", "").startswith("application/json")
            )
            if is_ajax:
                return JsonResponse({"error": "vault_locked"}, status=403)
            messages.warning(request, "Cofre bloqueado. Informe o PIN para continuar.")
            return redirect("cofre_senhas:index")

        touch_vault_session(request)
        return view_func(request, *args, **kwargs)

    return _wrapped