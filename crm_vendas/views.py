import json
import csv
import calendar
import datetime
from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.http import JsonResponse
from django.db.models import Q, Sum, Count, F, FloatField
from django.db.models.functions import TruncDay, Cast
from django.utils import timezone
from .models import Lead, HistoricoMovimentacao, AnotacaoLead, MotivoPerda, VendaPessoal, MetaUsuario, Segmento
from .forms import LeadForm
from django.core.paginator import Paginator

def check_is_supervisor(user):
    return user.is_superuser or user.groups.filter(name__in=['Admins', 'Irrestrito', 'Gerente Comercial']).exists()

@login_required
def kanban_vendas(request):
    is_supervisor = check_is_supervisor(request.user)
    vendedor_filtro = request.GET.get('vendedor')
    
    if is_supervisor:
        leads_brutos = Lead.objects.filter(ativo=True).exclude(etapa__in=['0_PROSPECCAO', '6_GANHO', '7_PERDIDO'])
    else:
        # 🔥 MÁGICA: Vendedor vê os leads dele OU os que ainda não têm dono (órfãos da IA)
        leads_brutos = Lead.objects.filter(
            Q(vendedor_responsavel=request.user) | Q(vendedor_responsavel__isnull=True),
            ativo=True
        ).exclude(etapa__in=['0_PROSPECCAO', '6_GANHO', '7_PERDIDO'])

    if vendedor_filtro:
        leads_brutos = leads_brutos.filter(vendedor_responsavel__id=vendedor_filtro)

    etapas_kanban = {
        '1_LEAD': {'titulo': 'Lead Recebido', 'leads': [], 'total_dinheiro': 0},
        '2_CONTATO': {'titulo': 'Primeiro Contato', 'leads': [], 'total_dinheiro': 0},
        '3_DIAGNOSTICO': {'titulo': 'Diagnóstico Técnico', 'leads': [], 'total_dinheiro': 0},
        '4_PROPOSTA': {'titulo': 'Proposta Enviada', 'leads': [], 'total_dinheiro': 0},
        '5_NEGOCIACAO': {'titulo': 'Negociação', 'leads': [], 'total_dinheiro': 0},
    }

    for lead in leads_brutos:
        coluna = etapas_kanban.get(lead.etapa)
        if coluna is not None:
            coluna['leads'].append(lead)
            coluna['total_dinheiro'] += float(lead.valor_ticket_medio or 0)

    from django.contrib.auth import get_user_model
    User = get_user_model()
    vendedores = User.objects.filter(is_active=True).filter(
        Q(groups__name__icontains='comercial') | 
        Q(groups__name__icontains='venda') | 
        Q(is_superuser=True)
    ).distinct().order_by('first_name')

    form_novo_lead = LeadForm(initial={'vendedor_responsavel': request.user})
    motivos_perda = MotivoPerda.objects.filter(ativo=True)

    return render(request, 'crm_vendas/kanban.html', {
        'etapas_kanban': etapas_kanban, 
        'is_supervisor': is_supervisor,
        'form_novo_lead': form_novo_lead, 
        'motivos_perda': motivos_perda,
        'vendedores': vendedores,
        'vendedor_atual': vendedor_filtro
    })

from django.core.paginator import Paginator # Adicione esta linha no topo do arquivo se não existir

@login_required
def lista_prospeccoes(request):
    def get_param(key, default=''):
        val = request.GET.get(key, default)
        return '' if val in ('None', 'none', None) else val

    busca_nome      = get_param('busca_nome')
    cidade_filtro   = get_param('cidade')
    segmento_filtro = get_param('segmento')
    vendedor_filtro = get_param('vendedor')
    data_inicio     = get_param('data_inicio')
    data_fim        = get_param('data_fim')
    ordenacao       = get_param('ordem') or '-data_criacao'
    itens_por_pagina = request.GET.get('itens_pagina', '20')
    
    hoje = timezone.now().date()
    
    leads = Lead.objects.filter(
        etapa='0_PROSPECCAO', 
        ativo=True
    ).filter(
        Q(data_prevista_reciclagem__isnull=True) | Q(data_prevista_reciclagem__lte=hoje)
    ).order_by(ordenacao)
    
    if busca_nome: leads = leads.filter(Q(nome_empresa__icontains=busca_nome) | Q(nome_contato__icontains=busca_nome))
    if data_inicio: leads = leads.filter(data_criacao__date__gte=data_inicio)
    if data_fim: leads = leads.filter(data_criacao__date__lte=data_fim)
    if cidade_filtro: leads = leads.filter(cidade=cidade_filtro)
    if segmento_filtro: leads = leads.filter(segmento_id=segmento_filtro)
    
    if vendedor_filtro == 'sem_vendedor':
        leads = leads.filter(vendedor_prospeccao__isnull=True)
    elif vendedor_filtro:
        leads = leads.filter(vendedor_prospeccao__id=vendedor_filtro)
    
    # --- PAGINAÇÃO ---
    try:
        itens_por_pagina = int(itens_por_pagina)
    except ValueError:
        itens_por_pagina = 20
        
    paginator = Paginator(leads, itens_por_pagina)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    # -----------------
    
    cidades = Lead.objects.filter(etapa='0_PROSPECCAO', ativo=True).exclude(cidade__isnull=True).exclude(cidade='').values_list('cidade', flat=True).distinct().order_by('cidade')
    segmentos = Segmento.objects.filter(ativo=True).order_by('nome')

    from django.contrib.auth import get_user_model
    User = get_user_model()
    vendedores = User.objects.filter(is_active=True).filter(
        Q(groups__name__icontains='comercial') | 
        Q(groups__name__icontains='venda') | 
        Q(is_superuser=True)
    ).distinct().order_by('first_name')

    form_novo_lead = LeadForm(initial={'vendedor_responsavel': request.user})

    # Contadores exibidos no topo da Mesa de Prospecção.
    # Antes era preciso filtrar a lista para descobrir quantos contatos ainda
    # estão livres para alguém pegar e quantos são do próprio vendedor.
    base_prospeccao = Lead.objects.filter(etapa='0_PROSPECCAO', ativo=True)

    context = {
        'leads': page_obj, # Enviamos a página em vez do queryset bruto
        'form_novo_lead': form_novo_lead, 
        'cidades': cidades, 'segmentos': segmentos, 'vendedores': vendedores,
        'busca_nome': busca_nome, 'itens_pagina': itens_por_pagina,
        'cidade_atual': cidade_filtro, 'segmento_atual': segmento_filtro, 'vendedor_atual': vendedor_filtro,
        'total_sem_dono': base_prospeccao.filter(vendedor_prospeccao__isnull=True).count(),
        'total_meus': base_prospeccao.filter(vendedor_prospeccao=request.user).count(),
    }
    return render(request, 'crm_vendas/lista_prospeccoes.html', context)

@login_required
def lista_perdidos(request):
    is_supervisor = check_is_supervisor(request.user)
    if is_supervisor: leads = Lead.objects.filter(etapa='7_PERDIDO', ativo=True).order_by('-data_fechamento')
    else: leads = Lead.objects.filter(etapa='7_PERDIDO', vendedor_responsavel=request.user, ativo=True).order_by('-data_fechamento')
    form_novo_lead = LeadForm(initial={'vendedor_responsavel': request.user})
    motivos_perda = MotivoPerda.objects.filter(ativo=True)
    return render(request, 'crm_vendas/lista_perdidos.html', {'leads': leads, 'form_novo_lead': form_novo_lead, 'motivos_perda': motivos_perda})

@login_required
def lista_ganhos(request):
    is_supervisor = check_is_supervisor(request.user)
    if is_supervisor: leads = Lead.objects.filter(etapa='6_GANHO', ativo=True).order_by('-data_fechamento')
    else: leads = Lead.objects.filter(etapa='6_GANHO', vendedor_responsavel=request.user, ativo=True).order_by('-data_fechamento')
    form_novo_lead = LeadForm(initial={'vendedor_responsavel': request.user})
    motivos_perda = MotivoPerda.objects.filter(ativo=True)
    return render(request, 'crm_vendas/lista_ganhos.html', {'leads': leads, 'form_novo_lead': form_novo_lead, 'motivos_perda': motivos_perda})

@login_required
@require_POST
def atualizar_etapa_lead(request):
    try:
        data = json.loads(request.body)
        lead = get_object_or_404(Lead, id=data.get('lead_id'))
        nova_etapa = data.get('nova_etapa')
        
        if lead.etapa == '0_PROSPECCAO' and not lead.vendedor_responsavel:
            lead.vendedor_responsavel = request.user

        if lead.etapa != nova_etapa:
            lead.etapa = nova_etapa
            lead.save()
            HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao=f"Moveu para {nova_etapa}", detalhes="Via Kanban/Tabela")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e: return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_POST
def lead_create_ajax(request):
    form = LeadForm(request.POST)
    if form.is_valid():
        lead = form.save(commit=False)
        if not lead.vendedor_responsavel:
            lead.vendedor_responsavel = request.user
        lead.save()
        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Criou o Lead", detalhes=f"Lead inserido na etapa: {lead.get_etapa_display()}")
        return JsonResponse({'status': 'sucesso'})
    else:
        return JsonResponse({'status': 'erro', 'erros': form.errors}, status=400)

@login_required
@require_POST
def importar_leads_csv(request):
    if 'arquivo_csv' not in request.FILES:
        return JsonResponse({'status': 'erro', 'message': 'Nenhum arquivo enviado.'}, status=400)
    arquivo = request.FILES['arquivo_csv']
    try:
        linhas = arquivo.read().decode('utf-8-sig').splitlines()
        delimitador = ';' if ';' in linhas[0] else ','
        leitor = csv.DictReader(linhas, delimiter=delimitador)
        
        if leitor.fieldnames:
            leitor.fieldnames = [str(name).strip().lower() for name in leitor.fieldnames]
            
        sucesso = 0
        for linha in leitor:
            empresa = str(linha.get('empresa', '')).strip()
            if empresa:
                segmento_str = str(linha.get('segmento', '')).strip()[:100]
                segmento_obj = None
                if segmento_str:
                    segmento_obj = Segmento.objects.filter(nome__iexact=segmento_str).first()
                    if not segmento_obj:
                        segmento_obj = Segmento.objects.create(nome=segmento_str)

                lead = Lead.objects.create(
                    nome_empresa=empresa, 
                    cnpj=str(linha.get('cnpj', '')).strip()[:18],
                    nome_contato=str(linha.get('contato', '')).strip() or 'Não informado', 
                    telefone=str(linha.get('telefone', '')).strip()[:20], 
                    cidade=str(linha.get('cidade', '')).strip()[:100], 
                    segmento=segmento_obj,
                    observacao_rapida=str(linha.get('observacao', '')).strip(),
                    origem='SITE', etapa='0_PROSPECCAO'
                )
                HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Importado via CSV")
                sucesso += 1
                
        if sucesso == 0:
            cabecalhos = ", ".join(leitor.fieldnames) if leitor.fieldnames else "Nenhum"
            mensagem_erro = f'O sistema leu as seguintes colunas no seu arquivo: [{cabecalhos}]. Para funcionar, a primeira coluna precisa se chamar exatamente: empresa'
            return JsonResponse({'status': 'erro', 'message': mensagem_erro})
            
        return JsonResponse({'status': 'sucesso', 'message': f'{sucesso} contatos importados com sucesso para o radar!'})
    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': f'Erro ao processar o arquivo: {str(e)}'}, status=400)

@login_required
@require_POST
def assumir_prospeccao_ajax(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    lead.vendedor_prospeccao = request.user
    lead.data_prospeccao = timezone.now()
    lead.save()
    HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Assumiu o Contato na Prospecção")
    return JsonResponse({'status': 'sucesso', 'nome': request.user.first_name or request.user.username, 'data': lead.data_prospeccao.strftime("%d/%m")})

@login_required
@require_POST
def descartar_prospeccao_ajax(request, lead_id):
    try:
        data = json.loads(request.body)
        motivo = data.get('motivo', 'Não informado')
        
        lead = get_object_or_404(Lead, id=lead_id)
        lead.ativo = False
        lead.detalhe_perda = motivo  # Salvando o motivo no banco
        lead.save()
        
        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Descartou Prospecção", detalhes=f"Motivo: {motivo}")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_POST
def salvar_obs_prospeccao_ajax(request, lead_id):
    data = json.loads(request.body)
    lead = get_object_or_404(Lead, id=lead_id)
    lead.observacao_rapida = data.get('texto', '')
    lead.save()
    return JsonResponse({'status': 'sucesso'})

@login_required
@require_POST
def prorrogar_sla_lead(request, lead_id):
    try:
        data = json.loads(request.body)
        motivo = data.get('motivo', '').strip()
        if not motivo: return JsonResponse({'status': 'erro', 'message': 'Motivo obrigatório'}, status=400)
        
        lead = get_object_or_404(Lead, id=lead_id)
        agora = timezone.now()
        
        # MÁGICA: Se já passou do tempo (está vermelho), dá 24h a partir do momento ATUAL!
        if lead.data_limite_sla and lead.data_limite_sla < agora:
            lead.data_limite_sla = agora + datetime.timedelta(hours=24)
        # Se ainda estava no prazo e ele só quis estender a gordura, soma normal
        elif lead.data_limite_sla:
            lead.data_limite_sla += datetime.timedelta(hours=24)
        else:
            lead.data_limite_sla = agora + datetime.timedelta(hours=24)
            
        lead.motivo_extensao_sla = motivo
        lead.save()
        
        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="SLA Prorrogado (+24h)", detalhes=f"Motivo: {motivo}")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e: 
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_GET
def get_lead_details(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    is_sup = check_is_supervisor(request.user)
    is_dono = lead.vendedor_responsavel == request.user or lead.vendedor_prospeccao == request.user
    pode_editar = is_sup or is_dono or not lead.vendedor_responsavel  # Se não tem dono, deixa preencher
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    vendedores_lista = [{'id': v.id, 'nome': v.get_full_name() or v.username} for v in User.objects.filter(is_active=True, groups__name__icontains='Comercial').distinct()]
    segmentos_lista = [{'id': s.id, 'nome': s.nome} for s in Segmento.objects.filter(ativo=True).order_by('nome')]
    
    eventos = []
    for hist in lead.historico.all(): eventos.append({'tipo': 'historico', 'obj': hist, 'data': hist.data_hora})
    for nota in lead.anotacoes.all(): eventos.append({'tipo': 'anotacao', 'obj': nota, 'data': nota.data_criacao})
    for arq in lead.arquivos.all(): eventos.append({'tipo': 'arquivo', 'obj': arq, 'data': arq.data_upload})
    eventos.sort(key=lambda x: x['data'], reverse=True)
    
    timeline = []
    for ev in eventos:
        obj = ev['obj']
        if ev['tipo'] == 'historico':
            timeline.append({'tipo': 'historico', 'texto': obj.acao, 'detalhes': obj.detalhes, 'vendedor': obj.vendedor.get_full_name() or obj.vendedor.username.capitalize() if obj.vendedor else 'Sistema', 'data': ev['data'].strftime("%d/%m/%Y %H:%M")})
        elif ev['tipo'] == 'anotacao':
            timeline.append({'tipo': 'anotacao', 'texto': obj.texto, 'vendedor': obj.vendedor.get_full_name() or obj.vendedor.username.capitalize() if obj.vendedor else 'Desconhecido', 'data': ev['data'].strftime("%d/%m/%Y %H:%M")})
        elif ev['tipo'] == 'arquivo':
            timeline.append({'tipo': 'arquivo', 'texto': f"📎 Arquivo Anexado: {obj.nome_arquivo}", 'url': obj.arquivo.url, 'vendedor': obj.vendedor.get_full_name() or obj.vendedor.username.capitalize() if obj.vendedor else 'Desconhecido', 'data': ev['data'].strftime("%d/%m/%Y %H:%M")})

    # ESSA É A PARTE QUE O SEU CÓDIGO ESTAVA IGNORANDO POR CAUSA DA DUPLICIDADE
    itens_proposta = []
    for item in lead.itens_proposta.all():
        itens_proposta.append({
            'id': item.id, 'tipo': item.tipo, 'nome': item.nome, 'valor': float(item.valor), 'quantidade': getattr(item, 'quantidade', 1)
        })

    data = {
        'id': str(lead.id),
        'nome_empresa': lead.nome_empresa,
        'nome_contato': lead.nome_contato,
        'vendedor': lead.vendedor_responsavel.get_full_name() or lead.vendedor_responsavel.username.capitalize() if lead.vendedor_responsavel else "Sem vendedor",
        'vendedor_id': lead.vendedor_responsavel.id if lead.vendedor_responsavel else "",
        'valor_total': float(lead.valor_ticket_medio or 0),
        'valor_mensalidade': float(getattr(lead, 'valor_mensalidade', 0) or 0),
        'valor_equipamentos_raw': float(lead.valor_equipamentos),
        'valor_servicos_raw': float(lead.valor_servicos),
        'forma_pagamento': lead.forma_pagamento or "",
        'prazo_pagamento': lead.prazo_pagamento or "",
        'telefone': lead.telefone or "Não informado",
        'cnpj': lead.cnpj or "Não informado",
        'cidade': getattr(lead, 'cidade', "Não informada"),
        'segmento_id': lead.segmento.id if getattr(lead, 'segmento', None) else "",
        'origem_display': lead.get_origem_display() if hasattr(lead, 'get_origem_display') else "Não informada",
        'urgencia_raw': lead.urgencia,
        'etapa_raw': lead.etapa,
        'urgencia_display': lead.get_urgencia_display() if hasattr(lead, 'get_urgencia_display') else "Normal",
        'dor_principal': lead.dor_principal or "",
        'etapa_display': lead.get_etapa_display(),
        'pode_editar': pode_editar,
        'is_supervisor': is_sup,
        'esta_atrasado': lead.esta_atrasado,
        'motivo_extensao_sla': lead.motivo_extensao_sla,
        'current_user_id': request.user.id,
        'vendedores_disp': vendedores_lista,
        'segmentos_disp': segmentos_lista,
        'timeline': timeline,
        'itens_proposta': itens_proposta 
    }
    return JsonResponse({'status': 'sucesso', 'data': data})

@login_required
@require_POST
def editar_lead_ajax(request, lead_id):
    try:
        data = json.loads(request.body)
        lead = get_object_or_404(Lead, id=lead_id)
        
        is_sup = check_is_supervisor(request.user)
        is_dono = lead.vendedor_responsavel == request.user or lead.vendedor_prospeccao == request.user
        
        if not (is_sup or is_dono) and lead.vendedor_responsavel:
            return JsonResponse({'status': 'erro', 'message': 'Sem permissão para editar.'}, status=403)

        lead.nome_empresa = data.get('nome_empresa', lead.nome_empresa)
        lead.nome_contato = data.get('nome_contato', lead.nome_contato)
        lead.telefone = data.get('telefone', lead.telefone)
        lead.cnpj = data.get('cnpj', lead.cnpj)
        lead.cidade = data.get('cidade', lead.cidade)
        lead.valor_mensalidade = data.get('valor_mensalidade', lead.valor_mensalidade)
        lead.valor_equipamentos = data.get('valor_equipamentos', lead.valor_equipamentos)
        lead.valor_servicos = data.get('valor_servicos', lead.valor_servicos)
        lead.forma_pagamento = data.get('forma_pagamento', lead.forma_pagamento)
        lead.prazo_pagamento = data.get('prazo_pagamento', lead.prazo_pagamento)
        lead.dor_principal = data.get('dor_principal', lead.dor_principal)
        lead.urgencia = data.get('urgencia', lead.urgencia)
        
        if data.get('segmento_id'): lead.segmento_id = data.get('segmento_id')

        novo_dono_id = data.get('vendedor_responsavel_id')
        if novo_dono_id and str(novo_dono_id) != str(lead.vendedor_responsavel_id if lead.vendedor_responsavel else ''):
            from django.contrib.auth import get_user_model
            User = get_user_model()
            novo_dono = User.objects.get(id=novo_dono_id)
            lead.vendedor_responsavel = novo_dono
            if lead.etapa == '0_PROSPECCAO':
                lead.vendedor_prospeccao = novo_dono
            HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao=f"Transferiu a posse do contato para {novo_dono.first_name or novo_dono.username}")

        nova_etapa = data.get('etapa', lead.etapa)
        if lead.etapa != nova_etapa:
            HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao=f"Moveu etapa para {nova_etapa}")
            lead.etapa = nova_etapa

        # Processamento dos Itens Dinâmicos
        itens_data = data.get('itens_proposta')
        if itens_data is not None:
            lead.itens_proposta.all().delete() # Limpa os antigos para recriar
            soma_produtos, soma_servicos, soma_mensalidade = 0, 0, 0
            
            from .models import ItemProposta
            for it in itens_data:
                val = float(it.get('valor', 0))
                qtd = int(it.get('quantidade', 1))
                tipo = it.get('tipo')
                
                ItemProposta.objects.create(lead=lead, tipo=tipo, nome=it.get('nome'), valor=val, quantidade=qtd)
                
                subtotal = val * qtd
                if tipo == 'PRODUTO': soma_produtos += subtotal
                elif tipo == 'SERVICO': soma_servicos += subtotal
                elif tipo == 'MENSALIDADE': soma_mensalidade += subtotal
                
            # Se ele adicionou itens detalhados, o sistema calcula os totais automaticamente!
            if len(itens_data) > 0:
                lead.valor_equipamentos = soma_produtos
                lead.valor_servicos = soma_servicos
                lead.valor_mensalidade = soma_mensalidade

        lead.save()

        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Editou as informações do negócio")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_POST
def upload_arquivo_lead(request, lead_id):
    try:
        lead = get_object_or_404(Lead, id=lead_id)
        if 'arquivo' not in request.FILES:
            return JsonResponse({'status': 'erro', 'message': 'Nenhum arquivo.'}, status=400)
            
        from .models import ArquivoProposta
        arquivo = request.FILES['arquivo']
        ArquivoProposta.objects.create(
            lead=lead, arquivo=arquivo, nome_arquivo=arquivo.name, vendedor=request.user
        )
        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao=f"Anexou o arquivo: {arquivo.name}")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_POST
def add_lead_note(request, lead_id):
    try:
        data = json.loads(request.body)
        texto = data.get('texto')
        if not texto: return JsonResponse({'status': 'erro', 'message': 'Texto vazio.'}, status=400)
        lead = get_object_or_404(Lead, id=lead_id)
        nota = AnotacaoLead.objects.create(lead=lead, vendedor=request.user, texto=texto, etapa_no_momento=lead.get_etapa_display())
        return JsonResponse({'status': 'sucesso', 'nota': {'texto': nota.texto, 'vendedor': nota.vendedor.get_full_name() or nota.vendedor.username, 'data': nota.data_criacao.strftime("%d/%m/%Y %H:%M")}})
    except Exception as e: return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
@require_POST
def fechar_lead(request, lead_id):
    try:
        data = json.loads(request.body)
        status_fechamento = data.get('status')
        lead = get_object_or_404(Lead, id=lead_id)
        
        if status_fechamento == 'GANHO':
            observacao = data.get('observacao', '').strip()
            lead.etapa = '6_GANHO'
            lead.data_fechamento = timezone.now()
            lead.save()
            
            texto_historico = f"Sucesso! 🏆 Detalhes: {observacao}" if observacao else "Sucesso! 🏆 Negócio Fechado."
            HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Marcou como GANHA 🏆", detalhes=texto_historico)
            
            # =========================================================
            # MÁGICA DE AUTOMAÇÃO: LANÇAR VENDAS NO PAINEL DO VENDEDOR
            # =========================================================
            vendedor_ganho = lead.vendedor_responsavel or request.user
            hoje = timezone.now().date()

            # Mapeia para o texto exato do seu painel "Minhas Vendas"
            tipo_map = {
                'PRODUTO': 'Equipamento',
                'SERVICO': 'Serviço',
                'MENSALIDADE': 'Mensalidade'
            }

            # Proteção contra erros de texto/vírgulas nos valores
            def safe_float(val):
                try:
                    if val is None or str(val).strip() == '': return 0.0
                    return float(val)
                except: return 0.0

            # Se detalhou os itens, lançamos um por um na meta!
            if lead.itens_proposta.exists():
                for item in lead.itens_proposta.all():
                    VendaPessoal.objects.create(
                        vendedor=vendedor_ganho,
                        tipo=tipo_map.get(item.tipo, 'Equipamento'),
                        valor=item.subtotal,
                        descricao=f"{lead.nome_empresa} - {item.nome}"[:200],
                        data_venda=hoje
                    )
            # Se não detalhou, lança o total geral das caixinhas
            else:
                val_eq = safe_float(lead.valor_equipamentos)
                if val_eq > 0:
                    VendaPessoal.objects.create(vendedor=vendedor_ganho, tipo="Equipamento", valor=val_eq, descricao=f"{lead.nome_empresa} - Equipamentos"[:200], data_venda=hoje)
                
                val_serv = safe_float(lead.valor_servicos)
                if val_serv > 0:
                    VendaPessoal.objects.create(vendedor=vendedor_ganho, tipo="Serviço", valor=val_serv, descricao=f"{lead.nome_empresa} - Serviços/Implantação"[:200], data_venda=hoje)
                
                val_mens = safe_float(lead.valor_mensalidade)
                if val_mens > 0:
                    VendaPessoal.objects.create(vendedor=vendedor_ganho, tipo="Mensalidade", valor=val_mens, descricao=f"{lead.nome_empresa} - Mensalidade"[:200], data_venda=hoje)
            # =========================================================
            
        elif status_fechamento == 'PERDIDO':
            motivo_id = data.get('motivo_id')
            detalhe = data.get('detalhe', '').strip()
            motivo = get_object_or_404(MotivoPerda, id=motivo_id)
            
            resgatar = data.get('resgatar', False)
            prazo_dias = int(data.get('prazo_resgate', 0) or 0)
            
            lead.etapa = '7_PERDIDO'
            lead.motivo_perda = motivo
            lead.detalhe_perda = detalhe
            lead.data_fechamento = timezone.now()
            lead.save()
            
            if resgatar and prazo_dias > 0:
                data_futura = timezone.now().date() + timedelta(days=prazo_dias)
                Lead.objects.create(
                    nome_empresa=f"{lead.nome_empresa} (Reciclagem)",
                    nome_contato=lead.nome_contato,
                    telefone=lead.telefone,
                    cnpj=lead.cnpj,
                    cidade=lead.cidade,
                    segmento=lead.segmento,
                    origem='RECICLAGEM',
                    etapa='0_PROSPECCAO',
                    data_prevista_reciclagem=data_futura,
                    observacao_rapida=f"Reciclado de: {lead.nome_empresa}. Motivo anterior: {motivo.nome}"
                )
            
            texto_historico = f"Motivo: {motivo.nome}."
            if detalhe:
                texto_historico += f" Observação: {detalhe}"
                
            HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Marcou como PERDIDA ❌", detalhes=texto_historico)
            
        return JsonResponse({'status': 'sucesso'})
    except Exception as e: 
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
@login_required
def minhas_vendas(request):
    hoje = date.today()
    mes_atual, ano_atual = hoje.month, hoje.year

    periodo = request.GET.get('periodo', 'mes')
    if periodo == '3': data_inicio = hoje - timedelta(days=90)
    elif periodo == '6': data_inicio = hoje - timedelta(days=180)
    else: data_inicio = hoje.replace(day=1)

    if request.method == 'POST':
        if 'atualizar_meta' in request.POST:
            valor = float(request.POST.get('valor_meta', 0).replace(',', '.'))
            MetaUsuario.objects.update_or_create(vendedor=request.user, mes=mes_atual, ano=ano_atual, defaults={'valor_meta': valor})
        elif 'adicionar_venda' in request.POST:
            VendaPessoal.objects.create(vendedor=request.user, tipo=request.POST.get('tipo'), valor=float(request.POST.get('valor', 0).replace(',', '.')), descricao=request.POST.get('descricao'), data_venda=hoje)
        return redirect(f"{request.path}?periodo={periodo}")

    vendas = VendaPessoal.objects.filter(vendedor=request.user, data_venda__gte=data_inicio).order_by('-data_venda')
    meta_obj = MetaUsuario.objects.filter(vendedor=request.user, mes=mes_atual, ano=ano_atual).first()
    valor_meta = float(meta_obj.valor_meta) if meta_obj else 0.0

    vendas_mes_atual = VendaPessoal.objects.filter(vendedor=request.user, data_venda__month=mes_atual, data_venda__year=ano_atual)
    total_geral = sum(float(v.valor) for v in vendas_mes_atual)
    
    porcentagem = round((total_geral / valor_meta * 100), 1) if valor_meta > 0 else 0
    falta = max(valor_meta - total_geral, 0)
    
    _, ultimo_dia = calendar.monthrange(ano_atual, mes_atual)
    dias_restantes = max((ultimo_dia - hoje.day) + 1, 1)
    meta_diaria = falta / dias_restantes if dias_restantes > 0 else 0

    trinta_dias_atras = hoje - timedelta(days=30)
    dados_grafico = VendaPessoal.objects.filter(vendedor=request.user, data_venda__gte=trinta_dias_atras).annotate(dia=TruncDay('data_venda')).values('dia').annotate(total=Sum('valor')).order_by('dia')
    
    labels_grafico = [d['dia'].strftime("%d/%m") for d in dados_grafico]
    valores_grafico = [float(d['total']) for d in dados_grafico]

    labels_mes = [str(i) for i in range(1, ultimo_dia + 1)]
    vendas_por_dia = {i: 0 for i in range(1, ultimo_dia + 1)}
    
    for v in vendas_mes_atual:
        vendas_por_dia[v.data_venda.day] += float(v.valor)
        
    dados_realizado = []
    acumulado = 0
    dia_atual_calculo = hoje.day if (hoje.month == mes_atual and hoje.year == ano_atual) else ultimo_dia
    
    for i in range(1, ultimo_dia + 1):
        if i <= dia_atual_calculo:
            acumulado += vendas_por_dia[i]
            dados_realizado.append(acumulado)
        else:
            dados_realizado.append(None)
            
    meta_por_dia = valor_meta / ultimo_dia if ultimo_dia > 0 else 0
    dados_meta_ideal = [round(meta_por_dia * i, 2) for i in range(1, ultimo_dia + 1)]
    
    dados_projecao = [None] * ultimo_dia
    if 0 < dia_atual_calculo < ultimo_dia:
        media_diaria_atual = acumulado / dia_atual_calculo
        dados_projecao[dia_atual_calculo - 1] = acumulado
        projecao_acumulada = acumulado
        for i in range(dia_atual_calculo, ultimo_dia):
            projecao_acumulada += media_diaria_atual
            dados_projecao[i] = round(projecao_acumulada, 2)

    context = {
        'vendas': vendas, 'total_geral': total_geral, 'valor_meta': valor_meta,
        'porcentagem_meta': porcentagem, 'falta_vender': falta,
        'meta_diaria_necessaria': meta_diaria, 'periodo': periodo,
        'labels_grafico': json.dumps(labels_grafico),
        'valores_grafico': json.dumps(valores_grafico),
        'labels_mes': json.dumps(labels_mes),
        'dados_realizado': json.dumps(dados_realizado),
        'dados_meta_ideal': json.dumps(dados_meta_ideal),
        'dados_projecao': json.dumps(dados_projecao),
    }
    return render(request, 'crm_vendas/minhas_vendas.html', context)

@login_required
def excluir_venda(request, venda_id):
    venda = get_object_or_404(VendaPessoal, id=venda_id, vendedor=request.user)
    venda.delete()
    return redirect('crm_vendas:minhas_vendas')

@login_required
@require_GET
def imprimir_proposta(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    context = {
        'lead': lead,
        'hoje': timezone.now()
    }
    return render(request, 'crm_vendas/proposta_impressao.html', context)

# ==============================================================================
# DASHBOARD GESTOR - POWER BI NATIVO (INTELIGÊNCIA REAL)
# ==============================================================================
# ==============================================================================
# DASHBOARD GESTOR - POWER BI NATIVO (INTELIGÊNCIA REAL)
# ==============================================================================
@login_required
def dashboard_gestor(request):
    if not check_is_supervisor(request.user):
        return redirect('crm_vendas:kanban')

    # ── FILTRO DE PERÍODO ──────────────────────────────────────────────────────
    filtro = request.GET.get('filtro', 'mes')
    hoje = timezone.now().date()

    if filtro == 'custom':
        try:
            data_inicio = date.fromisoformat(request.GET.get('data_inicio', ''))
            data_fim    = date.fromisoformat(request.GET.get('data_fim', ''))
        except (ValueError, TypeError):
            data_inicio = hoje.replace(day=1)
            data_fim    = hoje
        titulo_filtro = f"Personalizado: {data_inicio.strftime('%d/%m/%Y')} → {data_fim.strftime('%d/%m/%Y')}"
    elif filtro == '3m':
        data_inicio = hoje - timedelta(days=90)
        data_fim    = hoje
        titulo_filtro = "Últimos 3 Meses"
    elif filtro == '6m':
        data_inicio = hoje - timedelta(days=180)
        data_fim    = hoje
        titulo_filtro = "Últimos 6 Meses"
    elif filtro == '1a':
        data_inicio = hoje - timedelta(days=365)
        data_fim    = hoje
        titulo_filtro = "Último Ano"
    else:  # 'mes'
        data_inicio = hoje.replace(day=1)
        data_fim    = hoje
        titulo_filtro = f"Mês Atual ({hoje.strftime('%m/%Y')})"

    # ── BASE DE DADOS DO PERÍODO ───────────────────────────────────────────────
    leads_periodo = Lead.objects.filter(
        data_criacao__date__gte=data_inicio,
        data_criacao__date__lte=data_fim,
    )

    # ==========================================================================
    # ISOLAMENTO DA PROSPECÇÃO
    # ==========================================================================
    prospeccoes_ativas      = leads_periodo.filter(etapa='0_PROSPECCAO', ativo=True).count()
    prospeccoes_descartadas = leads_periodo.filter(etapa='0_PROSPECCAO', ativo=False).count()
    prospeccoes_convertidas = leads_periodo.exclude(etapa='0_PROSPECCAO').count()

    total_prospeccoes_brutas   = prospeccoes_ativas + prospeccoes_descartadas + prospeccoes_convertidas
    taxa_conversao_prospeccao  = round((prospeccoes_convertidas / total_prospeccoes_brutas * 100), 1) if total_prospeccoes_brutas > 0 else 0

    # ==========================================================================
    # FUNIL DE OPORTUNIDADES REAIS
    # ==========================================================================
    oportunidades = leads_periodo.exclude(etapa='0_PROSPECCAO')

    total_oportunidades   = oportunidades.count()
    ganhos_periodo        = oportunidades.filter(etapa='6_GANHO').count()
    taxa_conversao_vendas = round((ganhos_periodo / total_oportunidades * 100), 1) if total_oportunidades > 0 else 0

    receita_ganha = oportunidades.filter(etapa='6_GANHO').aggregate(
        total_mensalidade=Sum(Cast('valor_mensalidade', FloatField())),
        total_equipamentos=Sum(Cast('valor_equipamentos', FloatField())),
        total_servicos=Sum(Cast('valor_servicos', FloatField()))
    )
    mrr_total   = receita_ganha['total_mensalidade'] or 0.0
    setup_total = (receita_ganha['total_equipamentos'] or 0.0) + (receita_ganha['total_servicos'] or 0.0)

    pipeline_aberto = oportunidades.exclude(etapa__in=['6_GANHO', '7_PERDIDO']).aggregate(
        total=Sum(
            Cast('valor_mensalidade', FloatField()) +
            Cast('valor_equipamentos', FloatField()) +
            Cast('valor_servicos', FloatField())
        )
    )
    valor_pipeline       = pipeline_aberto['total'] or 0.0
    previsao_fechamento  = valor_pipeline * (taxa_conversao_vendas / 100)

    # ==========================================================================
    # GRÁFICOS
    # ==========================================================================
    dict_etapas = dict(Lead.ETAPAS_CHOICES)

    # Funil de passagem
    funil_etapas = (
        oportunidades
        .exclude(etapa__in=['6_GANHO', '7_PERDIDO'])
        .values('etapa').annotate(total=Count('id')).order_by('etapa')
    )
    labels_funil = [dict_etapas.get(e['etapa'], e['etapa'])[3:] for e in funil_etapas]
    dados_funil  = [e['total'] for e in funil_etapas]

    # Origem × Receita
    origens_cruzadas = oportunidades.values('origem').annotate(
        qtd=Count('id'),
        receita=Sum(
            Cast('valor_mensalidade', FloatField()) +
            Cast('valor_equipamentos', FloatField()) +
            Cast('valor_servicos', FloatField()),
            filter=Q(etapa='6_GANHO')
        )
    ).order_by('-qtd')
    dict_origens           = dict(Lead.ORIGEM_CHOICES)
    labels_origem_cruzada  = [dict_origens.get(o['origem'], o['origem']) for o in origens_cruzadas]
    dados_origem_qtd       = [o['qtd'] for o in origens_cruzadas]
    dados_origem_receita   = [float(o['receita'] or 0.0) for o in origens_cruzadas]

    # SLA estourado
    agora = timezone.now()
    atrasados_por_etapa = (
        oportunidades
        .exclude(etapa__in=['6_GANHO', '7_PERDIDO'])
        .filter(data_limite_sla__lt=agora)
        .values('etapa').annotate(total=Count('id'))
    )
    labels_sla = [dict_etapas.get(e['etapa'], e['etapa'])[3:] for e in atrasados_por_etapa]
    dados_sla  = [e['total'] for e in atrasados_por_etapa]

    # Motivos de perda
    perdas = (
        oportunidades
        .filter(etapa='7_PERDIDO', motivo_perda__isnull=False)
        .values('motivo_perda__nome').annotate(total=Count('id')).order_by('-total')[:6]
    )
    labels_motivos = [p['motivo_perda__nome'] for p in perdas]
    dados_motivos  = [p['total'] for p in perdas]

    # ==========================================================================
    # DESEMPENHO DA EQUIPE
    # ==========================================================================
    mes_atual, ano_atual = hoje.month, hoje.year
    metas = MetaUsuario.objects.filter(mes=mes_atual, ano=ano_atual).select_related('vendedor')
    desempenho_equipe = []

    for meta in metas:
        vendedor     = meta.vendedor
        valor_meta_v = float(meta.valor_meta)

        vendido_agregado = VendaPessoal.objects.filter(
            vendedor=vendedor,
            data_venda__gte=data_inicio,
            data_venda__lte=data_fim,
        ).aggregate(Sum('valor'))['valor__sum']
        total_vendido = float(vendido_agregado or 0)

        porcentagem   = round((total_vendido / valor_meta_v * 100), 1) if valor_meta_v > 0 else 0
        leads_abertos = Lead.objects.filter(vendedor_responsavel=vendedor).exclude(
            etapa__in=['0_PROSPECCAO', '6_GANHO', '7_PERDIDO']
        ).count()

        desempenho_equipe.append({
            'nome': vendedor.get_full_name() or vendedor.username.capitalize(),
            'meta': valor_meta_v, 'vendido': total_vendido,
            'porcentagem': porcentagem, 'leads_abertos': leads_abertos,
        })

    # ==========================================================================
    # ABA 4 — RELATÓRIO POR VENDEDOR
    # ==========================================================================
    from django.contrib.auth import get_user_model
    User = get_user_model()

    vendedores_ativos = User.objects.filter(is_active=True).filter(
        Q(groups__name__icontains='comercial') |
        Q(groups__name__icontains='venda') |
        Q(is_superuser=True)
    ).distinct().order_by('first_name')

    relatorio_vendedores = []

    for v in vendedores_ativos:
        filtro_periodo = dict(
            data_criacao__date__gte=data_inicio,
            data_criacao__date__lte=data_fim,
        )

        prosp_assumidas = Lead.objects.filter(
            vendedor_prospeccao=v, **filtro_periodo
        ).count()

        prosp_descartadas = Lead.objects.filter(
            vendedor_prospeccao=v, etapa='0_PROSPECCAO', ativo=False, **filtro_periodo
        ).count()

        prosp_qualificadas = Lead.objects.filter(
            vendedor_prospeccao=v, **filtro_periodo
        ).exclude(etapa='0_PROSPECCAO').count()

        motivo_descarte_top = Lead.objects.filter(
            vendedor_prospeccao=v, etapa='0_PROSPECCAO', ativo=False,
            detalhe_perda__isnull=False, **filtro_periodo
        ).exclude(detalhe_perda='').values('detalhe_perda').annotate(
            total=Count('id')
        ).order_by('-total').first()
        motivo_descarte_str = motivo_descarte_top['detalhe_perda'] if motivo_descarte_top else '—'

        interacoes = HistoricoMovimentacao.objects.filter(
            vendedor=v,
            data_hora__date__gte=data_inicio,
            data_hora__date__lte=data_fim,
        ).values('lead').distinct().count()

        leads_v = Lead.objects.filter(
            vendedor_responsavel=v, **filtro_periodo
        ).exclude(etapa='0_PROSPECCAO')

        em_diagnostico = leads_v.filter(etapa='3_DIAGNOSTICO').count()
        em_proposta    = leads_v.filter(etapa='4_PROPOSTA').count()
        em_negociacao  = leads_v.filter(etapa='5_NEGOCIACAO').count()
        ganhos_v       = leads_v.filter(etapa='6_GANHO').count()
        perdidos_v     = leads_v.filter(etapa='7_PERDIDO').count()

        total_fechados = ganhos_v + perdidos_v
        taxa_conv_v    = round((ganhos_v / total_fechados * 100), 1) if total_fechados > 0 else 0

        motivo_perda_top = leads_v.filter(
            etapa='7_PERDIDO', motivo_perda__isnull=False
        ).values('motivo_perda__nome').annotate(total=Count('id')).order_by('-total').first()
        motivo_perda_str = motivo_perda_top['motivo_perda__nome'] if motivo_perda_top else '—'

        receita_v = leads_v.filter(etapa='6_GANHO').aggregate(
            total=Sum(
                Cast('valor_equipamentos', FloatField()) +
                Cast('valor_mensalidade', FloatField()) +
                Cast('valor_servicos', FloatField())
            )
        )['total'] or 0.0

        meta_v_obj = MetaUsuario.objects.filter(vendedor=v, mes=mes_atual, ano=ano_atual).first()
        meta_v     = float(meta_v_obj.valor_meta) if meta_v_obj else 0.0
        perc_meta_v = round((receita_v / meta_v * 100), 1) if meta_v > 0 else 0

        if prosp_assumidas > 0 or ganhos_v > 0 or interacoes > 0:
            relatorio_vendedores.append({
                'nome': v.get_full_name() or v.username.capitalize(),
                'iniciais': (v.first_name[:1] + v.last_name[:1]).upper() if v.first_name and v.last_name else v.username[:2].upper(),
                'prosp_assumidas': prosp_assumidas,
                'prosp_qualificadas': prosp_qualificadas,
                'prosp_descartadas': prosp_descartadas,
                'motivo_descarte': motivo_descarte_str,
                'taxa_qualificacao': round((prosp_qualificadas / prosp_assumidas * 100), 1) if prosp_assumidas > 0 else 0,
                'interacoes': interacoes,
                'em_diagnostico': em_diagnostico,
                'em_proposta': em_proposta,
                'em_negociacao': em_negociacao,
                'ganhos': ganhos_v,
                'perdidos': perdidos_v,
                'taxa_conversao': taxa_conv_v,
                'motivo_perda_top': motivo_perda_str,
                'receita': receita_v,
                'meta': meta_v,
                'perc_meta': perc_meta_v,
            })

    relatorio_vendedores.sort(key=lambda x: x['receita'], reverse=True)

    context = {
        'filtro_ativo': filtro,
        'titulo_filtro': titulo_filtro,
        # Prospecção
        'total_prospeccoes_brutas': total_prospeccoes_brutas,
        'prospeccoes_ativas': prospeccoes_ativas,
        'prospeccoes_descartadas': prospeccoes_descartadas,
        'taxa_conversao_prospeccao': taxa_conversao_prospeccao,
        # Oportunidades
        'total_oportunidades': total_oportunidades,
        'taxa_conversao_vendas': taxa_conversao_vendas,
        'mrr_total': mrr_total,
        'setup_total': setup_total,
        'previsao_fechamento': previsao_fechamento,
        'valor_pipeline': valor_pipeline,
        # Gráficos
        'labels_funil': json.dumps(labels_funil),
        'dados_funil': json.dumps(dados_funil),
        'labels_origem_cruzada': json.dumps(labels_origem_cruzada),
        'dados_origem_qtd': json.dumps(dados_origem_qtd),
        'dados_origem_receita': json.dumps(dados_origem_receita),
        'labels_sla': json.dumps(labels_sla),
        'dados_sla': json.dumps(dados_sla),
        'labels_motivos': json.dumps(labels_motivos),
        'dados_motivos': json.dumps(dados_motivos),
        # Equipe
        'desempenho_equipe': desempenho_equipe,
        # Aba 4
        'relatorio_vendedores': relatorio_vendedores,
    }
    return render(request, 'crm_vendas/dashboard_gestor.html', context)

   # ==============================================================================
# MÓDULO EXCLUSIVO PARA MESA DE PROSPECÇÃO (ISOLADO DO KANBAN)
# ==============================================================================

@login_required
@require_GET
def get_prospeccao_details(request, prospeccao_id):
    lead = get_object_or_404(Lead, id=prospeccao_id)
    is_sup = check_is_supervisor(request.user)
    
    # Na prospecção, o dono é sempre o 'vendedor_prospeccao'
    is_dono = lead.vendedor_prospeccao == request.user
    pode_editar = is_sup or is_dono or not lead.vendedor_prospeccao
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    vendedores_lista = [{'id': v.id, 'nome': v.get_full_name() or v.username} for v in User.objects.filter(is_active=True, groups__name__icontains='Comercial').distinct()]
    segmentos_lista = [{'id': s.id, 'nome': s.nome} for s in Segmento.objects.filter(ativo=True).order_by('nome')]
    
    eventos = []
    for hist in lead.historico.all(): eventos.append({'tipo': 'historico', 'obj': hist, 'data': hist.data_hora})
    for nota in lead.anotacoes.all(): eventos.append({'tipo': 'anotacao', 'obj': nota, 'data': nota.data_criacao})
    eventos.sort(key=lambda x: x['data'], reverse=True)
    
    timeline = []
    for ev in eventos:
        obj = ev['obj']
        if ev['tipo'] == 'historico':
            timeline.append({'tipo': 'historico', 'texto': obj.acao, 'detalhes': obj.detalhes, 'vendedor': obj.vendedor.get_full_name() or obj.vendedor.username.capitalize() if obj.vendedor else 'Sistema', 'data': ev['data'].strftime("%d/%m/%Y %H:%M")})
        elif ev['tipo'] == 'anotacao':
            timeline.append({'tipo': 'anotacao', 'texto': obj.texto, 'vendedor': obj.vendedor.get_full_name() or obj.vendedor.username.capitalize() if obj.vendedor else 'Desconhecido', 'data': ev['data'].strftime("%d/%m/%Y %H:%M")})

    data = {
        'id': str(lead.id),
        'nome_empresa': lead.nome_empresa,
        'nome_contato': lead.nome_contato,
        'vendedor': lead.vendedor_prospeccao.get_full_name() or lead.vendedor_prospeccao.username.capitalize() if lead.vendedor_prospeccao else "Sem vendedor",
        'vendedor_id': lead.vendedor_prospeccao.id if lead.vendedor_prospeccao else "",
        'telefone': lead.telefone or "Não informado",
        'cnpj': lead.cnpj or "Não informado",
        'cidade': getattr(lead, 'cidade', "Não informada"),
        'segmento_id': lead.segmento.id if getattr(lead, 'segmento', None) else "",
        'urgencia_raw': lead.urgencia,
        'urgencia_display': lead.get_urgencia_display() if hasattr(lead, 'get_urgencia_display') else "Normal",
        'dor_principal': lead.dor_principal or "",
        'observacao_rapida': lead.observacao_rapida or "",
        'pode_editar': pode_editar,
        'is_supervisor': is_sup,
        'current_user_id': request.user.id,
        'vendedores_disp': vendedores_lista,
        'segmentos_disp': segmentos_lista,
        'timeline': timeline
    }
    return JsonResponse({'status': 'sucesso', 'data': data})

@login_required
@require_POST
def editar_prospeccao_ajax(request, prospeccao_id):
    try:
        data = json.loads(request.body)
        lead = get_object_or_404(Lead, id=prospeccao_id)
        
        is_sup = check_is_supervisor(request.user)
        is_dono = lead.vendedor_prospeccao == request.user
        
        # Bloqueio de Segurança para quem não é dono da prospecção
        if not (is_sup or is_dono) and lead.vendedor_prospeccao:
            return JsonResponse({'status': 'erro', 'message': 'Sem permissão para editar.'}, status=403)

        lead.nome_empresa = data.get('nome_empresa', lead.nome_empresa)
        lead.nome_contato = data.get('nome_contato', lead.nome_contato)
        lead.telefone = data.get('telefone', lead.telefone)
        lead.cnpj = data.get('cnpj', lead.cnpj)
        lead.cidade = data.get('cidade', lead.cidade)
        lead.dor_principal = data.get('dor_principal', lead.dor_principal)
        lead.urgencia = data.get('urgencia', lead.urgencia)
        
        if data.get('segmento_id'): lead.segmento_id = data.get('segmento_id')

        # Lógica de transferência isolada apenas para o vendedor da prospecção
        novo_dono_id = data.get('vendedor_responsavel_id')
        if novo_dono_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            novo_dono = User.objects.get(id=novo_dono_id)
            
            if lead.vendedor_prospeccao != novo_dono:
                lead.vendedor_prospeccao = novo_dono
                HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao=f"Transferiu o Contato para {novo_dono.first_name or novo_dono.username}")

        lead.save()
        HistoricoMovimentacao.objects.create(lead=lead, vendedor=request.user, acao="Editou as informações da Prospecção")
        return JsonResponse({'status': 'sucesso'})
    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
    
    # ✅ CORRETO - no nível raiz do arquivo
@login_required
def lista_descartadas(request):
    busca_nome = request.GET.get('busca_nome', '')

    leads = Lead.objects.filter(etapa='0_PROSPECCAO', ativo=False).order_by('-ultima_atualizacao')
    
    if busca_nome: 
        leads = leads.filter(Q(nome_empresa__icontains=busca_nome) | Q(nome_contato__icontains=busca_nome))
        
    from django.core.paginator import Paginator
    paginator = Paginator(leads, 40)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    
    return render(request, 'crm_vendas/lista_descartadas.html', {
        'leads': page_obj, 
        'busca_nome': busca_nome
    })