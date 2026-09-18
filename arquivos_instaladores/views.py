import os
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import F, Q, Sum, Count
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ArquivoItemForm
from .models import ArquivoItem, CategoriaChoices

from recompensas.utils import processar_acao_gamificada


# Pasta temporária para os pedaços enquanto o upload não termina.
CHUNK_TMP_DIR = "arquivos_instaladores/_chunks"


@login_required
def painel_listagem(request):
    q = request.GET.get("q", "").strip()
    cat = request.GET.get("categoria", "").strip()
    # Por padrão mostra ativos. ?ativos=0 mostra os arquivados.
    ativos = request.GET.get("ativos", "1") == "1"

    items = ArquivoItem.objects.select_related("criado_por")
    if q:
        items = items.filter(
            Q(titulo__icontains=q) | Q(descricao__icontains=q) | Q(versao__icontains=q)
        )
    if cat:
        items = items.filter(categoria=cat)
    items = items.filter(is_ativo=ativos)

    # Métricas reais (não inventadas): totais da base ativa.
    agregado = ArquivoItem.objects.filter(is_ativo=True).aggregate(
        n=Count("id"), espaco=Sum("tamanho_bytes"), baixados=Sum("downloads")
    )

    paginator = Paginator(items, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "arquivos_instaladores/painel_listagem.html", {
        "page_obj": page_obj,
        "q": q,
        "categoria": cat,
        "ativos": ativos,
        "categorias": CategoriaChoices.choices,
        "total_arquivos": agregado["n"] or 0,
        "espaco_total": agregado["espaco"] or 0,
        "total_downloads": agregado["baixados"] or 0,
    })


# ══════════════════════════════════════════════════════════════════
# UPLOAD EM PEDAÇOS (CHUNKED)
# ══════════════════════════════════════════════════════════════════
# Por que chunk e não upload normal:
#   - arquivo de 1GB num <form> comum trava a tela e estoura o timeout;
#   - o chunk (5MB por vez) dá barra de progresso REAL e libera o worker
#     entre os pedaços, então nunca fica 1GB preso num worker só —
#     protege o sistema inteiro independente de quantos workers existam.
#
# Fluxo:
#   1. o front cria o item (metadados) -> item_create devolve o pk
#   2. o front manda os pedaços em /upload/chunk/  (um POST por pedaço)
#   3. no último, chama /upload/finalizar/ -> junta, salva no FileField,
#      calcula o SHA256 em streaming e limpa os temporários.

@login_required
@permission_required("arquivos_instaladores.add_arquivoitem", raise_exception=True)
@require_POST
def upload_chunk(request):
    """Recebe UM pedaço. Salva em arquivo temporário identificado por upload_id."""
    upload_id = request.POST.get("upload_id", "")
    indice = request.POST.get("indice", "")
    pedaco = request.FILES.get("chunk")

    # valida upload_id para não permitir escrita fora da pasta temp
    if not pedaco or not indice.isdigit() or not _upload_id_valido(upload_id):
        return JsonResponse({"erro": "requisição inválida"}, status=400)

    nome_tmp = f"{CHUNK_TMP_DIR}/{upload_id}/{int(indice):06d}.part"
    default_storage.save(nome_tmp, ContentFile(pedaco.read()))
    return JsonResponse({"ok": True, "indice": int(indice)})


@login_required
@permission_required("arquivos_instaladores.add_arquivoitem", raise_exception=True)
@require_POST
def finalizar_upload(request):
    """Junta os pedaços, grava no item e calcula metadados."""
    upload_id = request.POST.get("upload_id", "")
    pk = request.POST.get("item_id", "")
    total = request.POST.get("total_chunks", "")
    filename = request.POST.get("filename", "arquivo.bin")

    if not _upload_id_valido(upload_id) or not pk.isdigit() or not total.isdigit():
        return JsonResponse({"erro": "requisição inválida"}, status=400)

    item = get_object_or_404(ArquivoItem, pk=int(pk), criado_por=request.user)
    total = int(total)
    prefixo = f"{CHUNK_TMP_DIR}/{upload_id}"

    # monta o caminho final e concatena os pedaços em streaming
    from .models import upload_to_categoria
    caminho_final = upload_to_categoria(item, filename)

    try:
        conteudo_final = default_storage.save(caminho_final, ContentFile(b""))
        # reescreve concatenando (append manual via storage local)
        destino_abs = default_storage.path(conteudo_final) if hasattr(default_storage, "path") else None

        if destino_abs:  # storage local (o caso do usuário: HD do servidor)
            with open(destino_abs, "wb") as saida:
                for i in range(total):
                    parte = f"{prefixo}/{i:06d}.part"
                    if not default_storage.exists(parte):
                        raise Http404(f"pedaço {i} ausente")
                    with default_storage.open(parte, "rb") as pf:
                        for bloco in iter(lambda: pf.read(4 * 1024 * 1024), b""):
                            saida.write(bloco)
        else:
            # fallback para storage remoto: monta em memória por partes
            from django.core.files.base import File
            import tempfile
            with tempfile.NamedTemporaryFile() as tmp:
                for i in range(total):
                    parte = f"{prefixo}/{i:06d}.part"
                    with default_storage.open(parte, "rb") as pf:
                        for bloco in iter(lambda: pf.read(4 * 1024 * 1024), b""):
                            tmp.write(bloco)
                tmp.seek(0)
                default_storage.delete(conteudo_final)
                conteudo_final = default_storage.save(caminho_final, File(tmp))

        # grava no item sem passar pelo save() pesado
        item.arquivo.name = conteudo_final
        item.tamanho_bytes = default_storage.size(conteudo_final)
        item.save(update_fields=["arquivo", "tamanho_bytes"])

        # SHA256 fora do caminho crítico do upload (streaming, 4MB por vez)
        item.checksum_sha256 = item.calcular_sha256_streaming()
        item.save(update_fields=["checksum_sha256"])

    finally:
        _limpar_chunks(prefixo, total)

    processar_acao_gamificada(
        usuario=request.user, acao="subir_arquivo", detalhe=f"Upload: {item.titulo}"
    )

    return JsonResponse({
        "ok": True,
        "redirect": "/arquivos-instaladores/",  # ajuste se o prefixo do include for outro
        "tamanho": item.tamanho_legivel,
    })


def _upload_id_valido(upload_id: str) -> bool:
    try:
        uuid.UUID(upload_id)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _limpar_chunks(prefixo: str, total: int):
    for i in range(total):
        parte = f"{prefixo}/{i:06d}.part"
        try:
            if default_storage.exists(parte):
                default_storage.delete(parte)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════════
@login_required
@permission_required("arquivos_instaladores.add_arquivoitem", raise_exception=True)
def item_create(request):
    """
    Cria o item (metadados). O ARQUIVO sobe depois, em chunks, via JS.
    Se o usuário optou por link externo, salva na hora e encerra.
    """
    if request.method == "POST":
        form = ArquivoItemForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.criado_por = request.user
            obj.save()

            # requisição AJAX (fluxo de upload de arquivo) → devolve o pk
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "item_id": obj.pk})

            # sem arquivo, só link externo
            messages.success(request, "Recurso cadastrado com sucesso.")
            return redirect("arquivos_instaladores:painel")
    else:
        form = ArquivoItemForm()

    return render(request, "arquivos_instaladores/item_form.html", {"form": form, "modo": "Novo"})


@login_required
@permission_required("arquivos_instaladores.change_arquivoitem", raise_exception=True)
def item_edit(request, pk):
    obj = get_object_or_404(ArquivoItem, pk=pk)
    if request.method == "POST":
        form = ArquivoItemForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "item_id": obj.pk})
            messages.success(request, "Recurso atualizado com sucesso.")
            return redirect("arquivos_instaladores:painel")
    else:
        form = ArquivoItemForm(instance=obj)

    return render(request, "arquivos_instaladores/item_form.html",
                  {"form": form, "modo": "Editar", "obj": obj})


@login_required
@permission_required("arquivos_instaladores.delete_arquivoitem", raise_exception=True)
def item_delete(request, pk):
    """
    Duas ações distintas, que ANTES eram uma só mentirosa (dizia 'excluir'
    mas só marcava inativo e o arquivo de 1GB ficava no HD para sempre):

      - Arquivar  (POST acao=arquivar): tira da lista, mantém o arquivo.
      - Excluir   (POST acao=excluir):  remove o registro E o arquivo do HD.
    """
    obj = get_object_or_404(ArquivoItem, pk=pk)

    if request.method == "POST":
        acao = request.POST.get("acao", "arquivar")
        if acao == "excluir":
            titulo = obj.titulo
            obj.delete()  # o signal apaga o arquivo físico
            messages.success(request, f"“{titulo}” foi excluído e o arquivo removido do servidor.")
        else:
            obj.is_ativo = False
            obj.save(update_fields=["is_ativo"])
            messages.info(request, f"“{obj.titulo}” foi arquivado (o arquivo continua no servidor).")
        return redirect("arquivos_instaladores:painel")

    return render(request, "arquivos_instaladores/item_delete_confirm.html", {"obj": obj})


@login_required
@permission_required("arquivos_instaladores.change_arquivoitem", raise_exception=True)
@require_POST
def item_restaurar(request, pk):
    obj = get_object_or_404(ArquivoItem, pk=pk)
    obj.is_ativo = True
    obj.save(update_fields=["is_ativo"])
    messages.success(request, f"“{obj.titulo}” foi restaurado.")
    return redirect("arquivos_instaladores:painel")


# ══════════════════════════════════════════════════════════════════
# DOWNLOAD (autenticado + contado)
# ══════════════════════════════════════════════════════════════════
@login_required
def item_download(request, pk):
    """
    Antes o card apontava direto para MEDIA_URL: sem contagem e, dependendo
    do storage, sem checagem de login. Agora o download passa por aqui —
    conta e (por estar sob @login_required) exige sessão.
    """
    obj = get_object_or_404(ArquivoItem, pk=pk)

    # link externo: conta e redireciona
    if not obj.tem_arquivo_local:
        if obj.link_externo:
            ArquivoItem.objects.filter(pk=pk).update(downloads=F("downloads") + 1)
            return redirect(obj.link_externo)
        raise Http404("Sem arquivo.")

    if not default_storage.exists(obj.arquivo.name):
        raise Http404("Arquivo não encontrado no servidor.")

    ArquivoItem.objects.filter(pk=pk).update(downloads=F("downloads") + 1)

    # FileResponse faz streaming — não carrega 1GB na RAM.
    # Em produção, o ideal é delegar ao nginx via X-Accel-Redirect; ver README.
    resposta = FileResponse(
        default_storage.open(obj.arquivo.name, "rb"),
        as_attachment=True,
        filename=obj.filename,
    )
    return resposta