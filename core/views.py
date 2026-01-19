from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q, Count, Max, Min
from datetime import date, datetime
import pandas as pd
from .models import LayoutArmazem, InventarioDiario, Produto, Cliente

# =============================================================================
# 1. DASHBOARD E MAPA (HOME)
# =============================================================================
def dashboard_armazem(request, galpao_id=0): # <--- CORRIGIDO: galpao_id
    # Filtros Básicos
    filtro_produto = request.GET.get('produto', '').strip()
    filtro_status = request.GET.get('status', '') 
    
    # Pega o último dia de inventário
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    data_ref = ultimo_registro.data_referencia if ultimo_registro else date.today()

    # Base de Ruas (Layout)
    ruas = LayoutArmazem.objects.all().order_by('gp', 'rua')
    if galpao_id > 0: # <--- Usando galpao_id
        ruas = ruas.filter(gp=galpao_id)

    # Base de Estoque (Apenas data mais recente)
    estoque = InventarioDiario.objects.filter(data_referencia=data_ref)
    
    # Monta o Mapa Visual
    mapa = []
    
    # Totais para os Cards
    total_geral = estoque.aggregate(Sum('quantidade_paletes'))['quantidade_paletes__sum'] or 0
    
    # Top Produtos
    top_produto = estoque.values('descricao').annotate(total=Sum('quantidade_paletes')).order_by('-total').first()
    bottom_produto = estoque.values('descricao').annotate(total=Sum('quantidade_paletes')).order_by('total').first()

    # Dicionário para acesso rápido ao estoque por Rua
    ocupacao_dict = {}
    for item in estoque:
        rid = item.rua.pk
        if rid not in ocupacao_dict:
            ocupacao_dict[rid] = {'produto': item.descricao, 'qtd': 0}
        
        ocupacao_dict[rid]['qtd'] += item.quantidade_paletes
        if ocupacao_dict[rid]['produto'] != item.descricao:
            ocupacao_dict[rid]['produto'] = "MISTO / VÁRIOS"

    # Constrói a lista final para o Template
    for rua in ruas:
        dados_estoque = ocupacao_dict.get(rua.pk, {'produto': '-', 'qtd': 0})
        ocupacao_atual = dados_estoque['qtd']
        produto_atual = dados_estoque['produto']
        
        # Filtros do Usuário
        if filtro_status == 'vazia' and ocupacao_atual > 0: continue
        if filtro_status == 'cheia' and ocupacao_atual < rua.cap_maxima: continue
        if filtro_produto and filtro_produto.upper() not in produto_atual.upper(): continue

        porcentagem = int((ocupacao_atual / rua.cap_maxima) * 100) if rua.cap_maxima > 0 else 0
        porcentagem = min(porcentagem, 100)

        # Cores Dinâmicas
        cor_bg = "bg-slate-800 border-slate-700"
        cor_bar = "bg-emerald-500"
        
        if porcentagem >= 90:
            cor_bg = "bg-rose-900/20 border-rose-500/50"
            cor_bar = "bg-rose-500"
        elif porcentagem == 0:
            cor_bg = "bg-slate-800/50 border-slate-700 opacity-75"
        
        mapa.append({
            'codigo': rua.rua,
            'gp': rua.gp,
            'capacidade': int(rua.cap_maxima),
            'ocupacao': int(ocupacao_atual),
            'porcentagem': porcentagem,
            'produto': produto_atual,
            'cor_bg': cor_bg,
            'cor_bar': cor_bar,
        })

    lista_galpoes = LayoutArmazem.objects.values_list('gp', flat=True).distinct().order_by('gp')

    return render(request, 'core/dashboard.html', {
        'mapa': mapa,
        'galpao': galpao_id, # <--- Enviando galpao_id
        'lista_galpoes': lista_galpoes,
        'total_geral': total_geral,
        'top_produto': top_produto,
        'bottom_produto': bottom_produto,
        'data_ref': data_ref,
        'filtro_produto': filtro_produto,
        'filtro_status': filtro_status,
        'titulo_galpao': f"Galpão {galpao_id}" if galpao_id > 0 else "Visão Global"
    })

# =============================================================================
# 2. UPLOAD DE EXCEL
# =============================================================================
def upload_inventario(request):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        
        try:
            df = pd.read_excel(arquivo)
            df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
            
            data_hoje = date.today()
            InventarioDiario.objects.filter(data_referencia=data_hoje).delete()
            
            registros = []
            for index, row in df.iterrows():
                rua_nome = str(row['rua'])
                rua_obj, _ = LayoutArmazem.objects.get_or_create(
                    rua=rua_nome,
                    defaults={'gp': 1, 'cap_maxima': 100, 'nivel': 1}
                )
                
                validade = row.get('validade')
                if pd.isnull(validade): validade = None
                
                producao = row.get('producao')
                if pd.isnull(producao): producao = None

                registros.append(InventarioDiario(
                    data_referencia=data_hoje,
                    rua=rua_obj,
                    sku=str(row['sku']),
                    descricao=row['descricao'],
                    quantidade_paletes=row['quantidade'],
                    data_validade=validade,
                    data_producao=producao,
                    lote=str(row.get('lote', '')),
                    status='DISPONIVEL'
                ))
            
            InventarioDiario.objects.bulk_create(registros)
            
            for reg in registros:
                Produto.objects.get_or_create(
                    sku=reg.sku,
                    defaults={'descricao': reg.descricao}
                )

            messages.success(request, f"Importação concluída! {len(registros)} itens carregados.")
            return redirect('home')

        except Exception as e:
            messages.error(request, f"Erro ao processar arquivo: {str(e)}")
            return redirect('upload')

    return render(request, 'core/upload.html')

# =============================================================================
# 3. RELATÓRIO FEFO (CORRIGIDO PARA BUSCAR DADOS RECENTES)
# =============================================================================
def radar_fefo(request):
    # Pega o último dia com dados
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    if not ultimo_registro:
        # Se não tiver dados nenhum, renderiza vazio
        return render(request, 'core/fefo.html', {'lista': []})
    
    data_ref = ultimo_registro.data_referencia
    hoje = date.today()

    # Busca itens DESSA data específica
    itens = InventarioDiario.objects.filter(
        data_referencia=data_ref, 
        data_validade__isnull=False
    ).select_related('rua').order_by('data_validade')
    
    fefo_data = []
    for item in itens:
        dias = (item.data_validade - hoje).days
        status_cor = "bg-emerald-500"
        if dias < 30: status_cor = "bg-red-600 animate-pulse"
        elif dias < 90: status_cor = "bg-amber-500"
        
        fefo_data.append({
            'item': item,
            'dias_vencimento': dias,
            'status_cor': status_cor
        })

    return render(request, 'core/fefo.html', {'lista': fefo_data})

# =============================================================================
# 4. PICKING (CORRIGIDO PARA BUSCAR DADOS RECENTES)
# =============================================================================
def picking_busca(request):
    termo = request.GET.get('q', '').strip()
    cliente_id = request.GET.get('cliente')
    
    resultados_finais = []
    lista_clientes = Cliente.objects.all() 
    cliente_selecionado = None

    if termo:
        # Pega data mais recente
        ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
        data_ref = ultimo_registro.data_referencia if ultimo_registro else date.today()

        itens_brutos = InventarioDiario.objects.filter(
            Q(sku__icontains=termo) | Q(descricao__icontains=termo),
            data_referencia=data_ref # <--- Filtro de Data Importante
        ).exclude(data_validade__isnull=True).select_related('rua').order_by('data_validade')

        if cliente_id:
            try:
                cliente = Cliente.objects.get(id=cliente_id)
                cliente_selecionado = cliente
                
                hoje = date.today()
                cache_produtos = {p.sku: p for p in Produto.objects.all()}

                for item in itens_brutos:
                    if not item.data_producao or not item.data_validade:
                        continue
                    
                    passou = False
                    if cliente.tipo_restricao == 'DIAS_PRODUCAO':
                        idade = (hoje - item.data_producao).days
                        if idade <= cliente.valor_restricao: passou = True
                    elif cliente.tipo_restricao == 'MIN_SHELF_LIFE':
                        prod_mestre = cache_produtos.get(item.sku)
                        if prod_mestre and prod_mestre.shelf_life_dias > 0:
                            dias_restantes = (item.data_validade - hoje).days
                            total = prod_mestre.shelf_life_dias
                            pct = (dias_restantes / total) * 100
                            if pct >= cliente.valor_restricao: passou = True
                        else:
                            passou = True

                    if passou: resultados_finais.append(item)
            except Cliente.DoesNotExist:
                resultados_finais = itens_brutos
        else:
            resultados_finais = itens_brutos

    return render(request, 'core/picking.html', {
        'termo': termo,
        'resultados': resultados_finais,
        'clientes': lista_clientes,
        'cliente_selecionado': cliente_selecionado
    })

# =============================================================================
# 5. OTIMIZAÇÃO (MANTIDO IGUAL, JÁ ESTAVA CORRETO)
# =============================================================================
def sugestao_consolidacao(request):
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    if not ultimo_registro:
        return render(request, 'core/consolidacao.html', {'sugestoes': [], 'qtd_oportunidades': 0, 'ganho_ruas': 0, 'pct_otimizacao': 0})
        
    data_ref = ultimo_registro.data_referencia
    estoque = InventarioDiario.objects.filter(data_referencia=data_ref).select_related('rua')
    
    mapa_ocupacao = {}
    for item in estoque:
        rid = item.rua.pk
        mapa_ocupacao[rid] = mapa_ocupacao.get(rid, 0) + item.quantidade_paletes

    grupos = {}
    for item in estoque:
        data_val = item.data_validade.strftime('%Y-%m-%d') if item.data_validade else 'ND'
        chave = f"{item.sku}|{data_val}"
        if chave not in grupos: grupos[chave] = []
        grupos[chave].append(item)

    sugestoes = []
    ruas_envolvidas = set()

    for chave, itens_brutos in grupos.items():
        if len(itens_brutos) < 2: continue

        itens_por_rua = {}
        for item in itens_brutos:
            nome_rua = str(item.rua.rua).strip()
            if nome_rua not in itens_por_rua:
                itens_por_rua[nome_rua] = item
            else:
                itens_por_rua[nome_rua].quantidade_paletes += item.quantidade_paletes
        
        itens = list(itens_por_rua.values())
        sku, data_val = chave.split('|')
        descricao_produto = itens[0].descricao
        itens.sort(key=lambda x: x.quantidade_paletes)

        for i in range(len(itens)):
            origem = itens[i]
            if origem.rua.pk in ruas_envolvidas: continue
            if origem.quantidade_paletes == 0: continue

            for j in range(len(itens)):
                if i == j: continue 
                
                destino = itens[j]
                if destino.rua.pk in ruas_envolvidas: continue
                
                if str(origem.rua.rua).strip() == str(destino.rua.rua).strip(): continue

                ocupacao_destino = mapa_ocupacao.get(destino.rua.pk, 0)
                cap_max = destino.rua.cap_maxima
                espaco_livre = cap_max - ocupacao_destino
                
                if espaco_livre >= (origem.quantidade_paletes - 0.1):
                    destino_antes = int(ocupacao_destino)
                    destino_depois = int(ocupacao_destino + origem.quantidade_paletes)
                    
                    sugestoes.append({
                        'produto': descricao_produto,
                        'sku': sku,
                        'validade': data_val,
                        'qtd_mover': int(origem.quantidade_paletes),
                        'origem_rua': origem.rua.rua,
                        'origem_gp': origem.rua.gp,
                        'destino_rua': destino.rua.rua,
                        'destino_gp': destino.rua.gp,
                        'origem_rua_id': origem.rua.pk,
                        'destino_rua_id': destino.rua.pk,
                        'destino_cap': int(cap_max),
                        'destino_antes': destino_antes,
                        'destino_depois': destino_depois,
                        'ganho': f"Esvazia Rua {origem.rua.rua}"
                    })
                    
                    mapa_ocupacao[destino.rua.pk] += origem.quantidade_paletes 
                    mapa_ocupacao[origem.rua.pk] -= origem.quantidade_paletes 
                    ruas_envolvidas.add(origem.rua.pk)
                    ruas_envolvidas.add(destino.rua.pk)
                    break 

    qtd_sugestoes = len(sugestoes)
    total_ruas_ocupadas = estoque.values('rua').distinct().count()
    pct_otimizacao = 0
    if total_ruas_ocupadas > 0:
        pct_otimizacao = (qtd_sugestoes / total_ruas_ocupadas) * 100

    movimentos_feitos = request.session.get('movimentos_feitos', [])

    return render(request, 'core/consolidacao.html', {
        'sugestoes': sugestoes,
        'qtd_oportunidades': qtd_sugestoes,
        'ganho_ruas': qtd_sugestoes,
        'pct_otimizacao': pct_otimizacao,
        'total_ocupadas': total_ruas_ocupadas,
        'movimentos_feitos': movimentos_feitos
    })

# =============================================================================
# 6. AÇÃO: REALIZAR MOVIMENTAÇÃO (MANTIDO IGUAL)
# =============================================================================
def realizar_consolidacao(request):
    if request.method == "POST":
        origem_rua_id = request.POST.get('origem_rua_id')
        destino_rua_id = request.POST.get('destino_rua_id')
        sku = request.POST.get('sku')
        data_validade_str = request.POST.get('validade')
        
        produto_nome = request.POST.get('produto_nome')
        origem_nome = request.POST.get('origem_nome')
        destino_nome = request.POST.get('destino_nome')
        qtd = request.POST.get('qtd')
        gp_origem = request.POST.get('gp_origem')
        gp_destino = request.POST.get('gp_destino')

        try:
            ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
            if not ultimo: return redirect('consolidacao')
            data_ref = ultimo.data_referencia

            itens_origem = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=origem_rua_id, sku=sku)
            if data_validade_str and data_validade_str != 'ND':
                itens_origem = itens_origem.filter(data_validade=data_validade_str)

            if itens_origem.exists():
                total_mover = sum(item.quantidade_paletes for item in itens_origem)
                
                item_destino = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=destino_rua_id, sku=sku).first()
                if item_destino and data_validade_str and data_validade_str != 'ND':
                     item_destino = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=destino_rua_id, sku=sku, data_validade=data_validade_str).first()

                if item_destino:
                    item_destino.quantidade_paletes += total_mover
                    item_destino.save()
                else:
                    ref = itens_origem.first()
                    rua_dest_obj = LayoutArmazem.objects.get(pk=destino_rua_id)
                    InventarioDiario.objects.create(
                        data_referencia=data_ref, rua=rua_dest_obj, sku=ref.sku, descricao=ref.descricao,
                        quantidade_paletes=total_mover, data_validade=ref.data_validade,
                        data_producao=ref.data_producao, lote=ref.lote, tipo_produto=ref.tipo_produto, status=ref.status
                    )

                itens_origem.delete()

                feito = {
                    'produto': produto_nome,
                    'sku': sku,
                    'origem_rua': origem_nome,
                    'destino_rua': destino_nome,
                    'qtd': qtd,
                    'gp_origem': gp_origem,
                    'gp_destino': gp_destino,
                    'hora': date.today().strftime('%d/%m')
                }
                
                historico = request.session.get('movimentos_feitos', [])
                historico.insert(0, feito)
                request.session['movimentos_feitos'] = historico
                
                messages.success(request, "Movimentação registrada com sucesso!")
            
        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")

    return redirect('consolidacao')