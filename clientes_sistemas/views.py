import re
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from .models import Cliente
from .forms import ClienteForm
from django.db.models import Q, Count
from django.contrib.auth.decorators import login_required
from sistemas.models import Sistema
from recompensas.utils import processar_acao_gamificada
from django.utils import timezone
import requests

@login_required
def painel_clientes(request):
    clientes = Cliente.objects.all()

    # ================================
    # FILTROS
    # ================================
    busca = request.GET.get("busca")
    status = request.GET.get("status")
    faturamento = request.GET.get("faturamento")
    sistema_id = request.GET.get("sistema")

    if busca:
        clientes = clientes.filter(
            Q(razao_social__icontains=busca) |
            Q(cnpj__icontains=busca)
        )

    if status:
        if status == "ativo":
            clientes = clientes.filter(ativo=True)
        elif status == "inativo":
            clientes = clientes.filter(ativo=False)

    if faturamento:
        clientes = clientes.filter(faturamento_cliente=faturamento)

    if sistema_id:
        clientes = clientes.filter(sistemas__id=sistema_id)

    # ================================
    # INDICADORES
    # ================================
    total = Cliente.objects.count()
    ativos = Cliente.objects.filter(ativo=True).count()
    com_contrato = Cliente.objects.filter(
        Q(contrato_software=True) | Q(contrato_hardware=True)
    ).count()
    backup = Cliente.objects.filter(backup_contratado=True).count()
    datacenter = Cliente.objects.filter(hospedagem_datacenter=True).count()
    classe_a = Cliente.objects.filter(faturamento_cliente="A").count()

    tef = Cliente.objects.filter(
        sistemas__nome__icontains="tef"
    ).distinct().count()

    todos_sistemas = Sistema.objects.all().order_by('nome')

    return render(request, "clientes_sistemas/painel_clientes.html", {
        "clientes": clientes.distinct(),
        "total": total,
        "ativos": ativos,
        "com_contrato": com_contrato,
        "backup": backup,
        "datacenter": datacenter,
        "classe_a": classe_a,
        "tef": tef,
        "todos_sistemas": todos_sistemas,
    })


@login_required
def cliente_create(request):
    if request.method == "POST":
        post_data = request.POST.copy()
        cnpj_digitado = post_data.get('cnpj', '')
        
        if cnpj_digitado:
            numeros = re.sub(r'\D', '', cnpj_digitado)
            if len(numeros) == 14:
                cnpj_formatado = f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
            elif len(numeros) == 11:
                cnpj_formatado = f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
            else:
                cnpj_formatado = numeros
                
            # Verifica o limpo e o formatado para evitar conflito com dados velhos
            if Cliente.objects.filter(Q(cnpj=cnpj_formatado) | Q(cnpj=numeros)).exists():
                from django.contrib import messages
                messages.error(request, f"ERRO: O CNPJ/CPF {cnpj_formatado} já possui cadastro no sistema!")
                return redirect("painel_clientes")
                
            # Passou no teste? Salva ele NO FORMATO PADRÃO
            post_data['cnpj'] = cnpj_formatado
            
        form = ClienteForm(post_data)
        if form.is_valid():
            cliente = form.save()
            cliente.calcular_health_score()
            
            processar_acao_gamificada(
                usuario=request.user, 
                acao='cadastrar_cliente',
                detalhe=f"Cliente: {cliente.razao_social}"
            )
            return redirect("painel_clientes")
    else:
        form = ClienteForm()

    return render(request, "clientes_sistemas/cliente_form.html", {"form": form})

@login_required
def cliente_edit(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)

    if request.method == "POST":
        post_data = request.POST.copy()
        cnpj_digitado = post_data.get('cnpj', '')
        
        if cnpj_digitado:
            numeros = re.sub(r'\D', '', cnpj_digitado)
            if len(numeros) == 14:
                cnpj_formatado = f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
            elif len(numeros) == 11:
                cnpj_formatado = f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
            else:
                cnpj_formatado = numeros
                
            # Trava na edição
            if Cliente.objects.filter(Q(cnpj=cnpj_formatado) | Q(cnpj=numeros)).exclude(pk=pk).exists():
                from django.contrib import messages
                messages.error(request, f"ERRO: O CNPJ/CPF {cnpj_formatado} já está em uso por outro cliente na base!")
                return redirect("painel_clientes")
                
            post_data['cnpj'] = cnpj_formatado
            
        form = ClienteForm(post_data, instance=cliente)
        if form.is_valid():
            form.save()
            cliente.calcular_health_score()
            return redirect("painel_clientes")
    else:
        form = ClienteForm(instance=cliente)

    return render(request, "clientes_sistemas/cliente_form.html", {"form": form})


@login_required
def buscar_cnpj(request):
    cnpj = request.GET.get("cnpj")

    if not cnpj:
        return JsonResponse({"erro": "CNPJ não informado"}, status=400)

    # Limpa a formatação (14 números puros)
    cnpj_limpo = "".join(filter(str.isdigit, cnpj))
    data_atual = timezone.now().strftime("%d/%m/%Y às %H:%M")

    # Disfarce para APIs não barrarem o servidor
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    # =================================================================================
    # TENTATIVA 1: API Open CNPJA (A mais rica, mas com rate limit)
    # =================================================================================
    try:
        r1 = requests.get(f"https://open.cnpja.com/office/{cnpj_limpo}", headers=headers, timeout=5)
        if r1.status_code == 200:
            data = r1.json()
            endereco = data.get("address", {})
            empresa = data.get("company", {})

            telefone = ""
            telefones_lista = data.get("phones", [])
            if telefones_lista:
                telefone = f"{telefones_lista[0].get('area', '')}{telefones_lista[0].get('number', '')}"

            email = ""
            emails_lista = data.get("emails", [])
            if emails_lista:
                email = emails_lista[0].get("address", "")

            ie = ""
            inscricoes = data.get("registrations") or []
            if inscricoes:
                ativa = next((r for r in inscricoes if r.get("enabled")), None)
                if ativa and ativa.get("number"):
                    ie = re.sub(r'\D', '', str(ativa.get("number")))
                else:
                    for r in inscricoes:
                        if r.get("number"):
                            ie = re.sub(r'\D', '', str(r.get("number")))
                            break

            is_simples = empresa.get("simples", {}).get("optant", False)
            regime = "Simples Nacional" if is_simples else "Lucro Presumido ou Real"

            return JsonResponse({
                "razao_social": empresa.get("name", ""),
                "nome_fantasia": data.get("alias", ""),
                "inscricao_estadual": ie,
                "cep": endereco.get("zip", ""),
                "logradouro": endereco.get("street", ""),
                "bairro": endereco.get("district", ""),
                "cidade": endereco.get("city", ""),
                "estado": endereco.get("state", ""),
                "telefone": telefone,
                "email": email,
                "regime_tributario": regime,
                "data_consulta": f"{data_atual} via Open CNPJA"
            })
    except Exception:
        pass # Se falhou por limite ou erro, segue silenciosamente para a próxima!

    # =================================================================================
    # TENTATIVA 2: Kitana OpenCNPJ (O Plano B que você trouxe)
    # =================================================================================
    try:
        r2 = requests.get(f"https://kitana.opencnpj.com/cnpj/{cnpj_limpo}", headers=headers, timeout=5)
        if r2.status_code == 200:
            resp2 = r2.json()
            if resp2.get("success"):
                data2 = resp2.get("data", {})
                return JsonResponse({
                    "razao_social": data2.get("razaoSocial", ""),
                    "nome_fantasia": data2.get("nomeFantasia", ""),
                    "inscricao_estadual": "", # Kitana não manda IE
                    "cep": re.sub(r'\D', '', str(data2.get("cep", ""))),
                    "logradouro": data2.get("logradouro", ""),
                    "bairro": data2.get("bairro", ""),
                    "cidade": data2.get("municipio", ""),
                    "estado": data2.get("uf", ""),
                    "telefone": re.sub(r'\D', '', str(data2.get("telefone", ""))),
                    "email": data2.get("email", ""),
                    "regime_tributario": "", # Kitana não manda Regime
                    "data_consulta": f"{data_atual} via Kitana CNPJ"
                })
    except Exception:
        pass # Se falhou, segue para o Plano C!

    # =================================================================================
    # TENTATIVA 3: BrasilAPI (O Fallback de Último Recurso)
    # =================================================================================
    try:
        r3 = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}", headers=headers, timeout=5)
        if r3.status_code == 200:
            data3 = r3.json()
            return JsonResponse({
                "razao_social": data3.get("razao_social", ""),
                "nome_fantasia": data3.get("nome_fantasia", ""),
                "inscricao_estadual": "",
                "cep": re.sub(r'\D', '', str(data3.get("cep", ""))),
                "logradouro": data3.get("logradouro", ""),
                "bairro": data3.get("bairro", ""),
                "cidade": data3.get("municipio", ""),
                "estado": data3.get("uf", ""),
                "telefone": re.sub(r'\D', '', str(data3.get("ddd_telefone_1", ""))),
                "email": data3.get("email", ""),
                "regime_tributario": "",
                "data_consulta": f"{data_atual} via BrasilAPI"
            })
    except Exception:
        pass

    # =================================================================================
    # FALHA TOTAL (Se a internet do servidor caiu ou TODAS as APIs morreram)
    # =================================================================================
    return JsonResponse({"erro": "Todas as bases públicas estão instáveis. Por favor, preencha manualmente."}, status=500)

@login_required
def toggle_status_financeiro(request, pk):
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=pk)
        
        # Inverte o status atual
        if cliente.status_financeiro == 'EM_DIA':
            cliente.status_financeiro = 'PENDENTE'
        else:
            cliente.status_financeiro = 'EM_DIA'
            
        cliente.save(update_fields=['status_financeiro'])
        
        # Registra a ação na gamificação
        processar_acao_gamificada(
            usuario=request.user, 
            acao='atualizar_financeiro',
            detalhe=f"Status alterado para {cliente.get_status_financeiro_display()} - {cliente.razao_social}"
        )
        
        return JsonResponse({
            'status': 'success', 
            'novo_status': cliente.status_financeiro
        })
        
    return JsonResponse({'status': 'invalid'}, status=400)