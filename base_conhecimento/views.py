# /base_conhecimento/views.py
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from sistemas.models import Sistema
from .models import Artigo, ArtigoAcesso
from .forms import ArtigoForm
from .sanitize import conteudo_seguro
from .toc import construir_toc

# === GATILHO DA GAMIFICAÇÃO ===
from recompensas.utils import processar_acao_gamificada


# ══════════════════════════════════════════════════════════════════
# ⚠️ NENHUMA view deste módulo tinha @login_required.
#
# A base de conhecimento inteira era pública — incluindo criar, editar
# e baixar o PDF que diz "confidencial e de uso restrito" no rodapé.
# Qualquer pessoa na internet podia abrir /base-conhecimento/ e ler,
# ou plantar um artigo com JavaScript malicioso (ver sanitize.py).
#
# Agora: leitura exige login; escrita exige permissão.
# ══════════════════════════════════════════════════════════════════


@login_required
def rom_base_conhecimento(request):
    """Página inicial: busca, atalhos e navegação por sistema."""
    # N+1 RESOLVIDO: o template chamava {{ sistema.artigos.count }} dentro
    # do loop -> uma query por sistema. Agora vem tudo numa query só.
    sistemas = (
        Sistema.objects.annotate(n_artigos=Count("artigos"))
        .order_by("nome")
    )

    # Suporte é 80/20: um punhado de artigos resolve a maioria das
    # chamadas. Antes eles eram reencontrados do zero toda vez.
    recentes = (
        Artigo.objects.filter(acessos__usuario=request.user)
        .select_related("sistema")
        .order_by("-acessos__visto_em")[:6]
    )

    populares = (
        Artigo.objects.filter(visualizacoes__gt=0)
        .select_related("sistema")
        .order_by("-visualizacoes")[:6]
    )

    return render(request, "base_conhecimento/rom.html", {
        "sistemas": sistemas,
        "total_artigos": Artigo.objects.count(),
        "recentes": recentes,
        "populares": populares,
    })


@login_required
def sistema_base_conhecimento(request, sistema_id: str):
    """Artigos de um sistema, com busca e paginação."""
    sistema = get_object_or_404(Sistema, pk=sistema_id)
    query = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()

    artigos = sistema.artigos.select_related("autor").order_by("-atualizado_em")

    if query:
        artigos = artigos.filter(filtro_busca(query))

    if tipo:
        artigos = artigos.filter(tipo=tipo)

    # Sem paginação, um sistema com 500 artigos renderizava 500 cards.
    paginator = Paginator(artigos, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "base_conhecimento/sistema.html", {
        "sistema": sistema,
        "artigos": page,
        "page_obj": page,
        "query": query,
        "tipo_atual": tipo,
        "tipos": Artigo.TIPOS,
        "total": paginator.count,
    })


@login_required
def artigo_detalhe(request, sistema_id: str, slug: str):
    sistema = get_object_or_404(Sistema, pk=sistema_id)
    artigo = get_object_or_404(
        Artigo.objects.select_related("autor", "sistema"),
        sistema=sistema, slug=slug,
    )

    _registrar_acesso(request.user, artigo)

    # o HTML passa pelo sanitizador ANTES de virar |safe; o índice é
    # construído em cima do HTML já limpo
    html_limpo = conteudo_seguro(artigo.conteudo)
    html_com_ancoras, toc = construir_toc(html_limpo)

    return render(request, "base_conhecimento/artigo_detalhe.html", {
        "sistema": sistema,
        "artigo": artigo,
        "hashtags": artigo.tags_lista,
        "conteudo_html": html_com_ancoras,
        "toc": toc,
    })


def _registrar_acesso(usuario, artigo):
    """
    Conta a visualização e marca o último acesso do usuário.

    Usa update()/F() para não disparar o save() do model e não mexer em
    `atualizado_em` — ler artigo não é editar artigo.
    """
    Artigo.objects.filter(pk=artigo.pk).update(visualizacoes=F("visualizacoes") + 1)

    acesso, criado = ArtigoAcesso.objects.get_or_create(
        usuario=usuario, artigo=artigo
    )
    if not criado:
        # `update()` não dispara o auto_now do visto_em, então setamos
        # explicitamente. F() evita race entre duas abas do mesmo usuário.
        ArtigoAcesso.objects.filter(pk=acesso.pk).update(
            vezes=F("vezes") + 1,
            visto_em=timezone.now(),
        )


@login_required
@permission_required("base_conhecimento.add_artigo", raise_exception=True)
def artigo_create(request, sistema_id: str):
    sistema = get_object_or_404(Sistema, pk=sistema_id)

    if request.method == "POST":
        form = ArtigoForm(request.POST)
        if form.is_valid():
            artigo = form.save(commit=False)
            artigo.sistema = sistema
            artigo.autor = request.user
            artigo.save()

            processar_acao_gamificada(
                usuario=request.user,
                acao="cadastrar_base_conhecimento",
                detalhe=f"Artigo: {artigo.titulo[:30]}",
            )

            return redirect("base_conhecimento:artigo_detalhe",
                            sistema_id=sistema.pk, slug=artigo.slug)
    else:
        form = ArtigoForm()

    return render(request, "base_conhecimento/artigo_form.html", {
        "form": form,
        "sistema": sistema,
        # BUG CORRIGIDO: o template testava {% if modo == 'Editar' %}, mas a
        # view mandava `edit_mode`. Como `modo` nunca existia, a tela de
        # edição sempre dizia "Novo Artigo". Agora o nome bate.
        "modo": "Criar",
    })


@login_required
@permission_required("base_conhecimento.change_artigo", raise_exception=True)
def artigo_edit(request, sistema_id: str, slug: str):
    sistema = get_object_or_404(Sistema, pk=sistema_id)
    artigo = get_object_or_404(Artigo, sistema=sistema, slug=slug)

    if request.method == "POST":
        form = ArtigoForm(request.POST, instance=artigo)
        if form.is_valid():
            artigo = form.save(commit=False)
            # o autor original é preservado: quem edita não "rouba" a autoria
            if not artigo.autor:
                artigo.autor = request.user
            artigo.save()
            return redirect("base_conhecimento:artigo_detalhe",
                            sistema_id=sistema.pk, slug=artigo.slug)
    else:
        form = ArtigoForm(instance=artigo)

    return render(request, "base_conhecimento/artigo_form.html", {
        "form": form,
        "sistema": sistema,
        "artigo": artigo,
        "modo": "Editar",
    })


@login_required
def artigo_pdf(request, sistema_id: str, slug: str):
    sistema = get_object_or_404(Sistema, pk=sistema_id)
    artigo = get_object_or_404(Artigo, sistema=sistema, slug=slug)

    html_string = render_to_string(
        "base_conhecimento/artigo_pdf.html",
        {
            "sistema": sistema,
            "artigo": artigo,
            "hashtags": artigo.tags_lista,
            "conteudo_html": conteudo_seguro(artigo.conteudo),
            "emitido_por": request.user.get_full_name() or request.user.username,
        },
        request=request,
    )

    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")
    # `inline` abre no navegador (o link usa target="_blank"); antes forçava
    # download de um arquivo que o usuário só queria ler.
    response["Content-Disposition"] = f'inline; filename="{artigo.codigo}_{artigo.slug}.pdf"'
    return response


# ══════════════════════════════════════════════════════════════════
# BUSCA
# ══════════════════════════════════════════════════════════════════
# A busca em `conteudo` só é ligada quando o campo está limpo de base64.
# Enquanto os artigos guardam screenshots embutidas (data:image/...;base64),
# um icontains varre MEGABYTES de ruído por registro e "png" casa com todo
# artigo que tem imagem.
#
# Rode `python manage.py extrair_imagens_base64` e ligue no settings:
#     BC_BUSCAR_NO_CONTEUDO = True
BUSCAR_NO_CONTEUDO = getattr(settings, "BC_BUSCAR_NO_CONTEUDO", False)


def filtro_busca(query: str) -> Q:
    """Monta o Q() de busca de artigo."""
    f = (
        Q(codigo__icontains=query)
        | Q(titulo__icontains=query)
        | Q(hashtags__icontains=query)
    )
    if BUSCAR_NO_CONTEUDO:
        f |= Q(conteudo__icontains=query)
    return f


@login_required
def busca_global(request):
    """
    Busca em TODOS os sistemas de uma vez.

    É a tela mais importante para quem está ao telefone: o cliente descreve
    o problema, não o sistema. Antes era preciso escolher o sistema primeiro
    e só então buscar — quem não sabia onde procurar, caçava um por um.
    """
    query = (request.GET.get("q") or "").strip()
    sistema_id = (request.GET.get("sistema") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()

    artigos = Artigo.objects.none()
    if query:
        artigos = (
            Artigo.objects.select_related("sistema", "autor")
            .filter(filtro_busca(query))
        )
        if sistema_id:
            artigos = artigos.filter(sistema_id=sistema_id)
        if tipo:
            artigos = artigos.filter(tipo=tipo)
        artigos = artigos.order_by("-atualizado_em")

    paginator = Paginator(artigos, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "base_conhecimento/busca.html", {
        "artigos": page,
        "page_obj": page,
        "query": query,
        "total": paginator.count if query else 0,
        "sistemas": Sistema.objects.order_by("nome"),
        "sistema_atual": sistema_id,
        "tipo_atual": tipo,
        "tipos": Artigo.TIPOS,
        "busca_no_conteudo": BUSCAR_NO_CONTEUDO,
    })