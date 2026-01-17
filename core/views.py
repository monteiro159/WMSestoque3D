import pandas as pd
from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum, Q  # <--- O Q ESTÁ AQUI
from .forms import UploadInventarioForm
from .models import InventarioDiario, LayoutArmazem, Produto, Cliente

# =============================================================================
# 1. FUNÇÃO DE UPLOAD
# =============================================================================
def upload_inventario(request):
    if request.method == "POST":
        form = UploadInventarioForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES['arquivo_excel']
            data_ref = form.cleaned_data['data_do_inventario']
            
            try:
                # Lê o Excel
                df = pd.read_excel(arquivo)
                df.columns = df.columns.str.strip().str.upper()
                
                col_endereco = next((c for c in df.columns if 'ENDERE' in c), None)
                if not col_endereco:
                    messages.error(request, "A coluna 'Endereço' não foi encontrada!")
                    return redirect('upload')

                objetos_para_salvar = []
                produtos_cache = {p.sku: p for p in Produto.objects.all()} 
                
                col_qtd = next((c for c in df.columns if c in ['QUANTIDADE', 'QTD', 'QTDE', 'SALDO']), None)
                if not col_qtd: col_qtd = df.columns[-1]

                for index, row in df.iterrows():
                    try:
                        cod_rua = int(row[col_endereco])
                        rua_obj = LayoutArmazem.objects.filter(rua=cod_rua).first()
                        if not rua_obj: continue 
                        
                        col_sku = 'ITEM' if 'ITEM' in df.columns else 'SKU'
                        sku_val = str(row.get(col_sku, '')).strip()
                        produto_mestre = produtos_cache.get(sku_val)

                        desc_val = str(row.get('MATERIAL', '')).strip()
                        if not desc_val and 'PRODUTO' in df.columns: 
                            desc_val = str(row.get('PRODUTO', '')).strip()

                        tipo_val = str(row.get('TIPO', '')).strip()
                        
                        if produto_mestre:
                            desc_val = produto_mestre.descricao 
                            if not tipo_val or pd.isna(tipo_val) or tipo_val == 'nan': 
                                tipo_val = produto_mestre.tipo 
                        
                        d_prod = pd.to_datetime(row.get('PRODUÇÃO'), dayfirst=True, errors='coerce')
                        if pd.isna(d_prod): d_prod = None
                        
                        col_validade = next((c for c in df.columns if 'VALIDADE' in c or 'VENCIMENTO' in c), None)
                        d_val = None
                        if col_validade:
                            d_val = pd.to_datetime(row.get(col_validade), dayfirst=True, errors='coerce')
                            if pd.isna(d_val): d_val = None

                        if d_prod and not d_val and produto_mestre and produto_mestre.shelf_life_dias > 0:
                            d_val = d_prod + timedelta(days=produto_mestre.shelf_life_dias)

                        try:
                            val_raw = row.get(col_qtd)
                            qtd = float(val_raw)
                            if pd.isna(qtd): qtd = 0.0
                        except:
                            qtd = 0.0

                        lote_virtual = f"{sku_val}_{d_prod.strftime('%Y%m%d')}" if d_prod else f"{sku_val}_ND"
                        if 'LOTE' in df.columns and pd.notnull(row.get('LOTE')):
                             lote_virtual = str(row.get('LOTE'))

                        obj = InventarioDiario(
                            data_referencia=data_ref,
                            rua=rua_obj,
                            sku=sku_val,
                            descricao=desc_val,
                            quantidade_paletes=qtd,
                            status=str(row.get('STATUS', 'ESTOQUE')),
                            tipo_produto=tipo_val,
                            data_validade=d_val,
                            data_producao=d_prod,
                            lote=lote_virtual
                        )
                        objetos_para_salvar.append(obj)

                    except: continue

                if objetos_para_salvar:
                    InventarioDiario.objects.filter(data_referencia=data_ref).delete()
                    InventarioDiario.objects.bulk_create(objetos_para_salvar)
                    messages.success(request, f"Sucesso! {len(objetos_para_salvar)} registros importados.")
                    return redirect('dashboard', galpao_id=1)
                else:
                    messages.warning(request, "Nenhum dado válido encontrado.")
            
            except Exception as e:
                messages.error(request, f"Erro crítico: {str(e)}")
                return redirect('upload')

    else:
        form = UploadInventarioForm()

    return render(request, 'core/upload.html', {'form': form})

# =============================================================================
# 2. DASHBOARD
# =============================================================================
def dashboard_armazem(request, galpao_id=1):
    filtro_produto = request.GET.get('produto', '').strip().lower()
    filtro_status = request.GET.get('status', '')

    galpoes_existentes = LayoutArmazem.objects.values_list('gp', flat=True).distinct().order_by('gp')
    
    ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
    data_ref = ultimo.data_referencia if ultimo else date.today()

    todos_itens = InventarioDiario.objects.filter(data_referencia=data_ref)
    stats_produtos = todos_itens.values('descricao').annotate(total=Sum('quantidade_paletes')).order_by('-total')
    top_produto = stats_produtos.first()
    bottom_produto = stats_produtos.last()
    total_geral = todos_itens.aggregate(Sum('quantidade_paletes'))['quantidade_paletes__sum'] or 0

    mapa_ruas = []
    
    if galpao_id == 0:
        ruas = LayoutArmazem.objects.all().order_by('gp', 'rua')
        titulo_galpao = "Visão Global"
    else:
        ruas = LayoutArmazem.objects.filter(gp=galpao_id).order_by('rua')
        titulo_galpao = f"Galpão {galpao_id}"

    itens_galpao = InventarioDiario.objects.filter(data_referencia=data_ref, rua__in=ruas)
    
    from collections import defaultdict
    itens_por_rua = defaultdict(list)
    for item in itens_galpao:
        itens_por_rua[item.rua_id].append(item)

    for rua in ruas:
        lista_itens = itens_por_rua.get(rua.rua, [])
        ocupacao = sum(i.quantidade_paletes for i in lista_itens)
        produto = lista_itens[0].descricao if lista_itens else "-"

        detalhes = []
        alerta_validade = False
        
        for item in lista_itens:
            dias_venc = 9999
            validade_str = "-"
            if item.data_validade:
                dias_venc = (item.data_validade - date.today()).days
                validade_str = item.data_validade.strftime('%Y-%m-%d')
                if dias_venc < 30: alerta_validade = True

            detalhes.append({
                'lote': item.lote or "S/ Lote",
                'qtd': int(item.quantidade_paletes),
                'validade': validade_str,
                'dias_venc': dias_venc,
                'status': item.status
            })
        
        detalhes.sort(key=lambda x: x['dias_venc'])
        pct = int((ocupacao / rua.cap_maxima) * 100) if rua.cap_maxima > 0 else 0
        
        cor_bg = "bg-emerald-600/20 border-emerald-500/50"
        cor_bar = "bg-emerald-500"
        if pct > 70: 
            cor_bg = "bg-amber-600/20 border-amber-500/50"
            cor_bar = "bg-amber-500"
        if pct >= 95: 
            cor_bg = "bg-rose-600/20 border-rose-500/50"
            cor_bar = "bg-rose-500"
        if alerta_validade:
            cor_bg = "bg-purple-600/20 border-purple-500"
        if ocupacao == 0: 
            cor_bg = "bg-slate-800/50 border-slate-700/50"
            cor_bar = "bg-slate-600"

        if filtro_produto and filtro_produto not in produto.lower(): continue
        if filtro_status == 'vazia' and ocupacao > 0: continue
        if filtro_status == 'cheia' and pct < 95: continue

        mapa_ruas.append({
            'codigo': rua.rua,
            'gp': rua.gp,
            'ocupacao': int(ocupacao),
            'capacidade': rua.cap_maxima,
            'porcentagem': pct,
            'cor_bg': cor_bg,
            'cor_bar': cor_bar,
            'produto': produto,
            'detalhes': detalhes,
            'alerta_validade': alerta_validade
        })

    return render(request, 'core/dashboard.html', {
        'galpao': galpao_id,
        'titulo_galpao': titulo_galpao,
        'data_ref': data_ref,
        'mapa': mapa_ruas,
        'filtro_produto': filtro_produto,
        'filtro_status': filtro_status,
        'lista_galpoes': galpoes_existentes,
        'top_produto': top_produto,
        'bottom_produto': bottom_produto,
        'total_geral': total_geral
    })

# =============================================================================
# 3. RADAR FEFO
# =============================================================================
def radar_fefo(request):
    filtro_status = request.GET.get('status', '')
    ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
    data_ref = ultimo.data_referencia if ultimo else date.today()
    hoje = date.today()

    kpi_vencidos = 0
    kpi_criticos = 0
    kpi_atencao = 0
    lista_fefo = []
    
    itens_raw = InventarioDiario.objects.filter(
        data_referencia=data_ref, 
        data_validade__isnull=False
    ).select_related('rua')

    for item in itens_raw:
        tipo_item = str(item.tipo_produto).strip().upper()
        if tipo_item != 'PA': continue 

        dias = (item.data_validade - hoje).days
        status_fefo = "ok"
        cor_badge = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
        
        if dias < 0:
            status_fefo = "vencido"
            cor_badge = "bg-rose-500/10 text-rose-400 border border-rose-500/20"
            kpi_vencidos += int(item.quantidade_paletes)
        elif dias <= 30:
            status_fefo = "critico"
            cor_badge = "bg-orange-500/10 text-orange-400 border border-orange-500/20 animate-pulse"
            kpi_criticos += int(item.quantidade_paletes)
        elif dias <= 90:
            status_fefo = "atencao"
            cor_badge = "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
            kpi_atencao += int(item.quantidade_paletes)

        if filtro_status and filtro_status != status_fefo: continue

        lista_fefo.append({
            'gp': item.rua.gp,
            'rua': item.rua.rua,
            'sku': item.sku,
            'produto': item.descricao,
            'lote': item.lote,
            'validade': item.data_validade,
            'dias': dias,
            'qtd': int(item.quantidade_paletes),
            'status': status_fefo,
            'cor': cor_badge
        })

    lista_fefo.sort(key=lambda x: x['dias'])

    context = {
        'lista_fefo': lista_fefo,
        'data_ref': data_ref,
        'kpi': {'vencidos': kpi_vencidos, 'criticos': kpi_criticos, 'atencao': kpi_atencao},
        'filtro_atual': filtro_status
    }
    return render(request, 'core/fefo.html', context)

# =============================================================================
# 4. PICKING / SUGESTÃO DE EXPEDIÇÃO
# =============================================================================
def picking_busca(request):
    termo = request.GET.get('q', '').strip()
    cliente_id = request.GET.get('cliente')
    
    resultados_finais = []
    # AQUI ESTÁ O SEGREDO: Buscamos os clientes para preencher o menu
    lista_clientes = Cliente.objects.all() 
    cliente_selecionado = None

    if termo:
        # 1. Busca Inicial (Traz tudo ordenado por FEFO - Data Validade)
        itens_brutos = InventarioDiario.objects.filter(
            Q(sku__icontains=termo) | Q(descricao__icontains=termo)
        ).exclude(data_validade__isnull=True).select_related('rua').order_by('data_validade')

        # 2. Se tiver Cliente selecionado no menu, aplica o Filtro de SLA
        if cliente_id:
            try:
                cliente = Cliente.objects.get(id=cliente_id)
                cliente_selecionado = cliente
                
                hoje = date.today()
                # Cache para não buscar no banco toda hora
                cache_produtos = {p.sku: p for p in Produto.objects.all()}

                for item in itens_brutos:
                    if not item.data_producao or not item.data_validade:
                        continue
                    
                    passou_na_regra = False
                    
                    # REGRA 1: IDADE MÁXIMA (Dias desde Produção)
                    if cliente.tipo_restricao == 'DIAS_PRODUCAO':
                        idade_do_produto = (hoje - item.data_producao).days
                        if idade_do_produto <= cliente.valor_restricao:
                            passou_na_regra = True
                    
                    # REGRA 2: % DE VIDA ÚTIL RESTANTE
                    elif cliente.tipo_restricao == 'MIN_SHELF_LIFE':
                        prod_mestre = cache_produtos.get(item.sku)
                        if prod_mestre and prod_mestre.shelf_life_dias > 0:
                            dias_restantes = (item.data_validade - hoje).days
                            total_vida = prod_mestre.shelf_life_dias
                            pct_restante = (dias_restantes / total_vida) * 100
                            
                            if pct_restante >= cliente.valor_restricao:
                                passou_na_regra = True
                        else:
                            passou_na_regra = True # Sem cadastro mestre, aprova por padrão

                    if passou_na_regra:
                        resultados_finais.append(item)
            
            except Cliente.DoesNotExist:
                resultados_finais = itens_brutos
        else:
            # Sem cliente? Mostra FEFO puro
            resultados_finais = itens_brutos

    return render(request, 'core/picking.html', {
        'termo': termo,
        'resultados': resultados_finais,
        'clientes': lista_clientes, # Agora a lista vai para o HTML!
        'cliente_selecionado': cliente_selecionado
    })
    # =============================================================================
# 5. CONSOLIDAÇÃO / OTIMIZAÇÃO DE ESPAÇO (NOVO)
# =============================================================================
def sugestao_consolidacao(request):
    # 1. Busca todo o estoque atual
    estoque = InventarioDiario.objects.select_related('rua').all()
    
    # 2. Agrupa por SKU + Validade (Chave Única)
    # Ex: 'HEINEKEN_2025-10-10' -> [ItemRua1, ItemRua2, ItemRua3]
    grupos = {}
    for item in estoque:
        # Cria uma chave única: SKU + Data de Validade (se houver)
        data_val = item.data_validade.strftime('%Y-%m-%d') if item.data_validade else 'ND'
        chave = f"{item.sku}|{data_val}"
        
        if chave not in grupos:
            grupos[chave] = []
        grupos[chave].append(item)

    sugestoes = []

    # 3. Analisa cada grupo procurando oportunidades
    for chave, itens in grupos.items():
        if len(itens) < 2: 
            continue # Se só tem em 1 lugar, não tem o que juntar
        
        # Separa SKU e Data para exibir bonito
        sku, data_val = chave.split('|')
        descricao_produto = itens[0].descricao
        
        # Ordena: Quem tem MENOS paletes primeiro (candidato a sair)
        # e quem tem MAIS espaço livre (candidato a receber)
        itens.sort(key=lambda x: x.quantidade_paletes)

        # Tenta combinar pares
        for i in range(len(itens)):
            origem = itens[i]
            if origem.quantidade_paletes == 0: continue

            for j in range(len(itens)):
                if i == j: continue # Não pode mover pra si mesmo
                
                destino = itens[j]
                
                # Capacidade da Rua de Destino
                cap_max = destino.rua.cap_maxima
                ocupacao_destino = sum(x.quantidade_paletes for x in estoque if x.rua == destino.rua)
                espaco_livre = cap_max - ocupacao_destino
                
                # A MÁGICA: Cabe tudo da origem no destino?
                # (Considerando uma margem de segurança de 0.1 para erros de float)
                if espaco_livre >= (origem.quantidade_paletes - 0.1):
                    
                    sugestoes.append({
                        'produto': descricao_produto,
                        'sku': sku,
                        'validade': data_val,
                        'qtd_mover': int(origem.quantidade_paletes),
                        'origem_rua': origem.rua.rua,
                        'origem_gp': origem.rua.gp,
                        'destino_rua': destino.rua.rua,
                        'destino_gp': destino.rua.gp,
                        'destino_livre': int(espaco_livre),
                        'ganho': f"Libera 100% da Rua {origem.rua.rua}"
                    })
                    
                    # Simula a mudança para não sugerir mover a mesma coisa duas vezes no loop
                    destino.quantidade_paletes += origem.quantidade_paletes
                    origem.quantidade_paletes = 0
                    break # Sai do loop interno e vai para o próximo item

    return render(request, 'core/consolidacao.html', {
        'sugestoes': sugestoes,
        'qtd_oportunidades': len(sugestoes)
    })