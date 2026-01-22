from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q, Count, Max, Min
from datetime import date, datetime
import pandas as pd
import unicodedata  # <--- O IMPORT QUE FALTAVA ESTÁ AQUI!

from .models import LayoutArmazem, InventarioDiario, Produto, Cliente

# =============================================================================
# 1. DASHBOARD (BASEADO NO BANCO DE DADOS - IMPORTADO VIA SCRIPT)
# =============================================================================
def dashboard_armazem(request, galpao_id=None):
    # 1. Busca Estoque
    data_hoje = date.today()
    itens = InventarioDiario.objects.filter(data_referencia=data_hoje)
    
    if not itens.exists():
        ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
        if ultimo:
            itens = InventarioDiario.objects.filter(data_referencia=ultimo.data_referencia)
            data_hoje = ultimo.data_referencia

    # 2. Filtros URL
    q_produto = request.GET.get('produto', '').strip()
    q_status = request.GET.get('status', '').strip()
    if q_produto: itens = itens.filter(descricao__icontains=q_produto)

    # 3. Carrega Mestre
    mapa_tipos = {p.sku: p.tipo for p in Produto.objects.all()}

    # 4. Inicializa Estatísticas
    stats = {
        'PA':     {'vol': 0.0, 'maior_item': None, 'maior_qtd': -1},
        'INSUMO': {'vol': 0.0, 'maior_item': None, 'maior_qtd': -1},
        'RPM':    {'vol': 0.0, 'maior_item': None, 'maior_qtd': -1}, # Caixas/Garrafas
        'PBR':    {'vol': 0.0, 'maior_item': None, 'maior_qtd': -1}, # Paletes Físicos
    }
    
    transitorio = {'vol': 0.0}
    ocupacao_por_rua = {}
    locais_transitorio = ['TRANSITORIO', 'TRANSITÓRIO', 'BOLSAO', 'EXTERNO', 'DOCA']

    for item in itens:
        sku = str(item.sku).strip()
        desc = item.descricao.upper()
        
        # A. DEFINIÇÃO DA CATEGORIA BASE (PA, INSUMO, RPM)
        tipo = mapa_tipos.get(sku)
        
        # Correções de Segurança (Dados sujos no nome)
        if 'SEM GARRAFA' in desc or 'VASILHAME' in desc or 'CASCO' in desc:
            tipo = 'RPM'
        
        if not tipo:
            # Fallback se não tiver no cadastro
            if desc.startswith('PLT') or 'CHAPATEX' in desc: tipo = 'RPM'
            elif 'BULK' in desc or 'LATA' in desc: tipo = 'INSUMO'
            else: tipo = 'PA'

        # B. SEPARAÇÃO FINA: RPM (Caixa) vs PBR (Palete)
        # O problema do Heineken "unpbr" acontecia aqui. Vamos ser restritos.
        
        categoria_final = tipo
        
        # Lista estrita de coisas que são ESTRUTURA (Card Roxo)
        eh_estrutura = False
        if 'PLT PBR' in desc or 'PALETE PBR' in desc or 'CHAPATEX' in desc or desc.startswith('PBR'):
            eh_estrutura = True
        
        # Lógica de Decisão
        if eh_estrutura:
            categoria_final = 'PBR'
        elif tipo == 'RPM':
            # Se é RPM mas não é estrutura (ex: caixa plástica, garrafa solta) -> Vai para Card RPM
            categoria_final = 'RPM'
        elif tipo == 'PA':
            # Se é PA, garante que fica em PA (não deixa cair em PBR por engano de string)
            categoria_final = 'PA'
            
        # Garante que a chave existe
        if categoria_final not in stats: categoria_final = 'PA'

        # C. CÁLCULO DE VOLUME
        qtd_inteira = int(item.quantidade_paletes)
        
        if categoria_final == 'PBR':
            # Paletes contam por Posição
            volume = item.quantidade_paletes
        else:
            # PA, INSUMO e RPM (Caixas) contam por Unidade de Venda
            volume = qtd_inteira + item.fracao

        # D. POPULA ESTATÍSTICAS
        stats[categoria_final]['vol'] += volume
        if volume > stats[categoria_final]['maior_qtd']:
            stats[categoria_final]['maior_qtd'] = volume
            stats[categoria_final]['maior_item'] = item
            
        # E. MAPA
        rid = item.rua.id
        if rid not in ocupacao_por_rua: ocupacao_por_rua[rid] = {'qtd': 0.0, 'produtos': set()}
        ocupacao_por_rua[rid]['qtd'] += item.quantidade_paletes
        ocupacao_por_rua[rid]['produtos'].add(item.descricao)

        if any(l in item.rua.rua.upper() for l in locais_transitorio):
            transitorio['vol'] += volume

    # 5. Visualização
    ruas_query = LayoutArmazem.objects.all().order_by('rua')
    if galpao_id: ruas_query = ruas_query.filter(gp=galpao_id)
    lista_galpoes = LayoutArmazem.objects.values_list('gp', flat=True).distinct().order_by('gp')

    mapa_visual = []
    for r in ruas_query:
        if any(l in r.rua.upper() for l in locais_transitorio): continue
        
        dados = ocupacao_por_rua.get(r.id, {'qtd': 0.0, 'produtos': []})
        ocupado = dados['qtd']
        pct = (ocupado / r.cap_maxima * 100) if r.cap_maxima > 0 else 0
        if pct > 100: pct = 100

        if ocupado <= 0:
            cor_bg = 'border-slate-800 bg-slate-900/50' 
            cor_bar = 'bg-slate-700'
            cor_texto = 'text-slate-600'
        elif pct >= 100:
            cor_bg = 'border-red-900/50 bg-red-900/10'
            cor_bar = 'bg-red-700'
            cor_texto = 'text-red-400'
        elif pct >= 85:
            cor_bg = 'border-blue-700/50 bg-blue-900/20'
            cor_bar = 'bg-blue-600'
            cor_texto = 'text-blue-400'
        else:
            cor_bg = 'border-emerald-800/50 bg-emerald-900/10'
            cor_bar = 'bg-emerald-600'
            cor_texto = 'text-emerald-400'

        mostrar = True
        if q_status == 'vazia' and ocupado > 0: mostrar = False
        if q_status == 'cheia' and pct < 85: mostrar = False

        if mostrar:
            prod_nome = list(dados['produtos'])[0] if dados['produtos'] else "-"
            if len(dados['produtos']) > 1: prod_nome = "MISTO"
            mapa_visual.append({
                'id': r.id, 'codigo': r.rua, 'gp': r.gp,
                'produto': prod_nome.title(), 'ocupacao': f"{ocupado:.1f}", 
                'capacidade': int(r.cap_maxima), 'porcentagem': int(pct),
                'cor_bg': cor_bg, 'cor_bar': cor_bar, 'cor_texto': cor_texto
            })

    return render(request, 'core/dashboard.html', {
        'mapa': mapa_visual, 'lista_galpoes': lista_galpoes,
        'galpao': galpao_id if galpao_id else 0,
        'titulo_galpao': f"Galpão {galpao_id}" if galpao_id else "Visão Global",
        'data_ref': data_hoje, 'stats': stats, 'transitorio': transitorio,
        'filtro_produto': q_produto, 'filtro_status': q_status
    })
# =============================================================================
# 2. UPLOAD DE EXCEL (VERSÃO FINAL QUE ACEITA TUDO)
# =============================================================================
def upload_inventario(request):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        
        try:
            df = pd.read_excel(arquivo)
            
            # Limpeza de Cabeçalho
            def limpar_header(texto):
                if isinstance(texto, str):
                    texto_sem_acento = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
                    return texto_sem_acento.lower().strip().replace(' ', '_').replace('.', '')
                return str(texto).lower().strip()

            df.columns = [limpar_header(c) for c in df.columns]
            
            # Mapeamento
            mapa_colunas = {
                'endereco': 'rua',
                'item': 'sku',
                'material': 'descricao',
                'lote_enchimento': 'lote',
                'producao_shelf': 'producao',
                'validade': 'validade',
                'quantidade': 'quantidade',
                'fracao': 'fracao',
                'status': 'status'
            }
            df.rename(columns=mapa_colunas, inplace=True)
            
            # Limpeza Geral
            data_hoje = date.today()
            InventarioDiario.objects.filter(data_referencia=data_hoje).delete()
            
            if 'movimentos_feitos' in request.session:
                del request.session['movimentos_feitos']
            
            registros = []
            ruas_novas = []

            for index, row in df.iterrows():
                rua_nome = str(row['rua']).strip()
                
                # --- CORREÇÃO AQUI ---
                # Removi 'tipo_palete' e 'empilhamento_max' pois não existem no LayoutArmazem
                # Mantive 'largura_colunas' pois é obrigatório
                rua_obj, created = LayoutArmazem.objects.get_or_create(
                    rua=rua_nome,
                    defaults={
                        'gp': 1,               
                        'cap_maxima': 100,     
                        'largura_colunas': 1.0, # Essencial para evitar o erro NOT NULL
                        'base_footprint': 1.0,
                        'cap_nivel_1': 0,
                        'cap_nivel_2': 0
                    }
                )
                if created: ruas_novas.append(rua_nome)
                
                # Tratamento de Validade e Produção
                validade = row.get('validade')
                if pd.isnull(validade) or str(validade).strip() == '': validade = None
                
                producao = row.get('producao')
                if pd.isnull(producao) or str(producao).strip() == '': producao = None

                # Lógica Decimal
                try: qtd_int = int(float(row.get('quantidade', 0)))
                except: qtd_int = 0

                try: fracao_int = int(float(row.get('fracao', 0)))
                except: fracao_int = 0
                
                # Lógica PBR vs Visual Decimal
                desc = str(row.get('descricao', '')).upper()
                
                # Nova regra: Se for PBR (Palete), divide fração por 15
                # Se for RPM/PA/INSUMO, usa decimal visual
                eh_pbr_fisico = 'PBR' in desc or 'PALETE' in desc
                
                if eh_pbr_fisico:
                    ocupacao_posicoes = qtd_int + (fracao_int / 15.0)
                else:
                    try: ocupacao_posicoes = float(f"{qtd_int}.{fracao_int}")
                    except: ocupacao_posicoes = 0.0

                registros.append(InventarioDiario(
                    data_referencia=data_hoje,
                    rua=rua_obj,
                    sku=str(row.get('sku', '')),
                    descricao=row.get('descricao', ''),
                    quantidade_paletes=ocupacao_posicoes,
                    fracao=fracao_int,
                    data_validade=validade,
                    data_producao=producao,
                    lote=str(row.get('lote', '')),
                    status=str(row.get('status', 'DISPONIVEL'))
                ))
            
            InventarioDiario.objects.bulk_create(registros)
            
            # Cria produtos que não existem
            for reg in registros:
                Produto.objects.get_or_create(sku=reg.sku, defaults={'descricao': reg.descricao})

            if ruas_novas:
                qtd_novas = len(ruas_novas)
                messages.warning(request, f"⚠️ Atenção: {qtd_novas} novas ruas criadas (ex: {ruas_novas[0]}).")
            else:
                messages.success(request, f"Sucesso! {len(registros)} itens importados.")
                
            return redirect('home')

        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")
            return redirect('upload')

    return render(request, 'core/upload.html')
# =============================================================================
# 3. RELATÓRIO FEFO
# =============================================================================
def radar_fefo(request):
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    if not ultimo_registro:
        return render(request, 'core/fefo.html', {'lista': [], 'kpis': {}})
    
    data_ref = ultimo_registro.data_referencia
    hoje = date.today()

    itens = InventarioDiario.objects.filter(
        data_referencia=data_ref, 
        data_validade__isnull=False
    ).select_related('rua').order_by('data_validade')
    
    fefo_data = []
    
    kpis = {
        'vencidos': 0, 'criticos': 0, 'atencao': 0, 'ok': 0, 'duraveis': 0
    }

    # === LISTA DE SKUs IMUNES (RPM/INSUMOS/BARRIS) ===
    # Coloquei como strings ('...') para garantir que bata com o banco de dados
    skus_duraveis = [
        '237857', '654013', '654014', '636878', '230121', '215443', '250985',
        '215442', '2154421', '2494', '24941', '49721', '49719', '107381',
        '1073811', '2482', '163974'
    ]

    for item in itens:
        # Verifica se o SKU do item está na lista de duráveis
        # Usamos str() e strip() para garantir que espaços vazios não atrapalhem
        sku_atual = str(item.sku).strip()
        eh_duravel = sku_atual in skus_duraveis

        if eh_duravel:
            # LÓGICA PARA INSUMOS (Não vence)
            dias_restantes = 9999 
            vida_total_dias = 100
            pct_restante = 100
            status_texto = "DURÁVEL"
            status_cor = "bg-blue-600" # Azul
            kpis['duraveis'] += item.quantidade_paletes
        
        else:
            # LÓGICA PADRÃO (PA - PRODUTO ACABADO)
            dias_restantes = (item.data_validade - hoje).days
            
            if item.data_producao:
                vida_total_dias = (item.data_validade - item.data_producao).days
            else:
                vida_total_dias = 180 
            
            if vida_total_dias <= 0: vida_total_dias = 1

            dias_vividos = vida_total_dias - dias_restantes
            pct_vivida = (dias_vividos / vida_total_dias) * 100
            pct_restante = 100 - pct_vivida

            # Definição de Status
            status_texto = "OK"
            status_cor = "bg-emerald-500"
            
            if dias_restantes < 0:
                status_texto = "VENCIDO"
                status_cor = "bg-rose-600 animate-pulse"
                kpis['vencidos'] += item.quantidade_paletes

            elif pct_restante <= 33: 
                status_texto = "CRÍTICO"
                status_cor = "bg-orange-600"
                kpis['criticos'] += item.quantidade_paletes

            elif pct_restante <= 66:
                status_texto = "ATENÇÃO"
                status_cor = "bg-amber-500"
                kpis['atencao'] += item.quantidade_paletes
            
            else:
                kpis['ok'] += item.quantidade_paletes

        fefo_data.append({
            'item': item,
            'dias_vencimento': dias_restantes,
            'vida_total': vida_total_dias,
            'pct_restante': int(pct_restante),
            'status_texto': status_texto,
            'status_cor': status_cor
        })
    
    # Ordena: Vencidos -> Críticos -> Atenção -> OK -> Duráveis
    prioridade_map = {'VENCIDO': 1, 'CRÍTICO': 2, 'ATENÇÃO': 3, 'OK': 4, 'DURÁVEL': 5}
    fefo_data.sort(key=lambda x: prioridade_map.get(x['status_texto'], 5))

    return render(request, 'core/fefo.html', {'lista': fefo_data, 'kpis': kpis})
# =============================================================================
# 4. PICKING
# =============================================================================
def picking_busca(request):
    termo = request.GET.get('q', '').strip()
    cliente_id = request.GET.get('cliente')
    
    resultados_finais = []
    lista_clientes = Cliente.objects.all() 
    cliente_selecionado = None

    if termo:
        ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
        data_ref = ultimo_registro.data_referencia if ultimo_registro else date.today()

        itens_brutos = InventarioDiario.objects.filter(
            Q(sku__icontains=termo) | Q(descricao__icontains=termo),
            data_referencia=data_ref 
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
# 5. OTIMIZAÇÃO
# =============================================================================
def sugestao_consolidacao(request):
    # 1. Validações Iniciais
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    if not ultimo_registro:
        return render(request, 'core/consolidacao.html', {
            'sugestoes': [], 'qtd_oportunidades': 0, 'ganho_ruas': 0, 'pct_otimizacao': 0
        })
        
    data_ref = ultimo_registro.data_referencia
    estoque = InventarioDiario.objects.filter(data_referencia=data_ref).select_related('rua')
    
    # 2. Mapa de Ocupação Atual (Ocupação Física no Chão)
    mapa_ocupacao = {}
    for item in estoque:
        rid = item.rua.pk
        mapa_ocupacao[rid] = mapa_ocupacao.get(rid, 0) + item.quantidade_paletes

    # 3. Carrega Dados de Empilhamento dos Produtos (Para evitar N+1 queries)
    # Cria um dicionário: {'SKU123': 3, 'SKU456': 2}
    mapa_empilhamento = {p.sku: p.empilhamento for p in Produto.objects.all()}

    # 4. Agrupamento por SKU + Validade
    grupos = {}
    for item in estoque:
        data_val = item.data_validade.strftime('%Y-%m-%d') if item.data_validade else 'ND'
        chave = f"{item.sku}|{data_val}"
        if chave not in grupos: grupos[chave] = []
        grupos[chave].append(item)

    sugestoes = []
    ruas_envolvidas = set()

    # 5. Algoritmo de Consolidação
    for chave, itens_brutos in grupos.items():
        if len(itens_brutos) < 2: continue

        # Agrupa itens que já estão na mesma rua (para somar qtd)
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
        
        # Pega o empilhamento do produto (Padrão 1 se não achar)
        stacking = mapa_empilhamento.get(sku, 1)

        # Ordena: Tenta esvaziar quem tem menos primeiro
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

                # === CÁLCULO DA CAPACIDADE DINÂMICA ===
                rua_obj = destino.rua
                
                # Base da rua (Footprint)
                base = rua_obj.base_footprint
                
                # Lógica de Segurança:
                # Se a base for <= 1 (configuração antiga/inválida), usamos a cap_maxima fixa como fallback.
                # Se a base estiver certa (ex: 42), multiplicamos pelo empilhamento do produto.
                if base > 1:
                    cap_real = base * stacking
                else:
                    cap_real = rua_obj.cap_maxima

                ocupacao_destino = mapa_ocupacao.get(destino.rua.pk, 0)
                espaco_livre = cap_real - ocupacao_destino
                
                # Verifica se cabe (com margem de segurança de 0.1 para flutuação)
                if espaco_livre >= (origem.quantidade_paletes - 0.1):
                    destino_antes = int(ocupacao_destino)
                    destino_depois = int(ocupacao_destino + origem.quantidade_paletes)
                    
                    sugestoes.append({
                        'produto': descricao_produto,
                        'sku': sku,
                        'validade': data_val,
                        'qtd_mover': float(origem.quantidade_paletes), # Garante float
                        'origem_rua': origem.rua.rua,
                        'origem_gp': origem.rua.gp,
                        'destino_rua': destino.rua.rua,
                        'destino_gp': destino.rua.gp,
                        'origem_rua_id': origem.rua.pk,
                        'destino_rua_id': destino.rua.pk,
                        'destino_cap': int(cap_real), # Mostra a capacidade REAL para este produto
                        'destino_antes': destino_antes,
                        'destino_depois': destino_depois,
                        'ganho': f"Esvazia Rua {origem.rua.rua}",
                        'motivo': f"Stack: {stacking}x" # Info extra visual
                    })
                    
                    # Atualiza simulação de ocupação
                    mapa_ocupacao[destino.rua.pk] += origem.quantidade_paletes 
                    mapa_ocupacao[origem.rua.pk] -= origem.quantidade_paletes 
                    
                    # Marca ruas como usadas nesta rodada para evitar conflito
                    ruas_envolvidas.add(origem.rua.pk)
                    ruas_envolvidas.add(destino.rua.pk)
                    break 

    # 6. Finalização e Contexto
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
# 6. AÇÃO: REALIZAR MOVIMENTAÇÃO
# =============================================================================
def realizar_consolidacao(request):
    if request.method == "POST":
        # Dados do Produto/Local
        origem_rua_id = request.POST.get('origem_rua_id')
        destino_rua_id = request.POST.get('destino_rua_id')
        sku = request.POST.get('sku')
        data_validade_str = request.POST.get('validade')
        qtd = float(request.POST.get('qtd'))
        
        # Dados de Rastreabilidade (NOVOS)
        supervisor = request.POST.get('supervisor', '').upper()
        operador = request.POST.get('operador', '').upper()

        # Dados apenas visuais para o histórico
        produto_nome = request.POST.get('produto_nome')
        origem_nome = request.POST.get('origem_nome')
        destino_nome = request.POST.get('destino_nome')
        gp_origem = request.POST.get('gp_origem')
        gp_destino = request.POST.get('gp_destino')

        try:
            ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
            if not ultimo: return redirect('consolidacao')
            data_ref = ultimo.data_referencia

            # 1. Busca na Origem
            itens_origem = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=origem_rua_id, sku=sku)
            if data_validade_str and data_validade_str != 'ND':
                itens_origem = itens_origem.filter(data_validade=data_validade_str)

            if itens_origem.exists():
                # Remove da Origem
                ref = itens_origem.first()
                total_mover = sum(item.quantidade_paletes for item in itens_origem)
                itens_origem.delete()

                # 2. Adiciona no Destino
                # Tenta achar item igual no destino para somar
                item_destino = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=destino_rua_id, sku=sku).first()
                if data_validade_str and data_validade_str != 'ND':
                     item_destino = InventarioDiario.objects.filter(data_referencia=data_ref, rua_id=destino_rua_id, sku=sku, data_validade=data_validade_str).first()

                if item_destino:
                    item_destino.quantidade_paletes += total_mover
                    item_destino.save()
                else:
                    # Se não tem, cria novo
                    rua_dest_obj = LayoutArmazem.objects.get(pk=destino_rua_id)
                    InventarioDiario.objects.create(
                        data_referencia=data_ref, rua=rua_dest_obj, sku=ref.sku, descricao=ref.descricao,
                        quantidade_paletes=total_mover, data_validade=ref.data_validade,
                        data_producao=ref.data_producao, lote=ref.lote, status=ref.status
                    )

                # 3. Salva no Histórico da Sessão
                feito = {
                    'id_unico': f"{origem_rua_id}-{destino_rua_id}-{sku}", # ID para poder desfazer depois
                    'produto': produto_nome,
                    'sku': sku,
                    'origem_rua': origem_nome, 'origem_id': origem_rua_id,
                    'destino_rua': destino_nome, 'destino_id': destino_rua_id,
                    'qtd': total_mover,
                    'validade': data_validade_str,
                    'gp_origem': gp_origem,
                    'gp_destino': gp_destino,
                    'supervisor': supervisor, # NOVO
                    'operador': operador,     # NOVO
                    'hora': datetime.now().strftime('%H:%M')
                }
                
                historico = request.session.get('movimentos_feitos', [])
                historico.insert(0, feito)
                request.session['movimentos_feitos'] = historico
                
                messages.success(request, f"Movimentado com sucesso! (Op: {operador})")
            
        except Exception as e:
            messages.error(request, f"Erro: {str(e)}")

    return redirect('consolidacao')

# =============================================================================
# 7. AÇÃO: DESFAZER MOVIMENTAÇÃO (UNDO)
# =============================================================================
def reverter_consolidacao(request):
    if request.method == "POST":
        # Pega os dados do movimento original para inverter
        origem_id_original = request.POST.get('origem_id')   # Era Origem, vai virar Destino
        destino_id_original = request.POST.get('destino_id') # Era Destino, vai virar Origem
        sku = request.POST.get('sku')
        qtd = float(request.POST.get('qtd'))
        validade = request.POST.get('validade')
        id_unico = request.POST.get('id_unico')

        try:
            ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
            data_ref = ultimo.data_referencia

            # A LÓGICA INVERSA: Tirar do Destino e devolver para Origem
            
            # 1. Tira do Destino (que agora tem o produto)
            item_no_destino = InventarioDiario.objects.filter(
                data_referencia=data_ref, rua_id=destino_id_original, sku=sku
            )
            if validade and validade != 'ND':
                item_no_destino = item_no_destino.filter(data_validade=validade)
            
            item_dest = item_no_destino.first()

            if item_dest and item_dest.quantidade_paletes >= qtd:
                # Subtrai a quantidade
                item_dest.quantidade_paletes -= qtd
                if item_dest.quantidade_paletes <= 0:
                    item_dest.delete()
                else:
                    item_dest.save()

                # 2. Devolve para a Origem
                rua_orig_obj = LayoutArmazem.objects.get(pk=origem_id_original)
                
                # Tenta achar se já tem algo lá (improvável se esvaziou, mas possível)
                item_na_origem = InventarioDiario.objects.filter(
                    data_referencia=data_ref, rua_id=origem_id_original, sku=sku
                ).first()

                if item_na_origem:
                    item_na_origem.quantidade_paletes += qtd
                    item_na_origem.save()
                else:
                    # Recria o item na origem (usando dados do item_dest como base para validade/lote)
                    InventarioDiario.objects.create(
                        data_referencia=data_ref, rua=rua_orig_obj, sku=sku, 
                        descricao=item_dest.descricao, quantidade_paletes=qtd, 
                        data_validade=item_dest.data_validade, data_producao=item_dest.data_producao,
                        lote=item_dest.lote, status=item_dest.status
                    )

                # 3. Remove do Histórico da Sessão
                historico = request.session.get('movimentos_feitos', [])
                # Filtra removendo o item com aquele ID
                historico = [h for h in historico if h.get('id_unico') != id_unico]
                request.session['movimentos_feitos'] = historico

                messages.info(request, "Movimentação desfeita com sucesso! Estoque devolvido.")
            else:
                messages.error(request, "Não foi possível desfazer. O saldo no destino já mudou.")

        except Exception as e:
            messages.error(request, f"Erro ao reverter: {str(e)}")

    return redirect('consolidacao')
# =============================================================================
# 8. UPLOAD DE CADASTRO DE PRODUTOS (MASTER DATA)
# =============================================================================
def upload_produtos(request):
    if request.method == 'POST' and request.FILES.get('arquivo_produtos'):
        arquivo = request.FILES['arquivo_produtos']
        
        try:
            # Lê o Excel
            df = pd.read_excel(arquivo)
            
            # Padroniza nomes das colunas (remove espaços e acentos)
            def limpar_coluna(col):
                return str(col).upper().strip()
            
            df.columns = [limpar_coluna(c) for c in df.columns]

            # Verifica se as colunas essenciais existem (Baseado na sua imagem)
            # SKU (A), PRODUTO (B), TIPO (E)
            # O Pandas pode ler 'SKU', 'PRODUTO', 'TIPO' se estiver no cabeçalho
            
            atualizados = 0
            criados = 0

            for index, row in df.iterrows():
                # Tratamento seguro dos dados
                sku = str(row.get('SKU', '')).strip().replace('.0', '') # Remove decimais de excel
                descricao = str(row.get('PRODUTO', '')).strip()
                tipo_bruto = str(row.get('TIPO', 'PA')).upper().strip()
                
                if not sku or sku == 'nan': continue

                # Normaliza o TIPO para bater com o sistema
                if 'INSUMO' in tipo_bruto:
                    tipo_final = 'INSUMO'
                elif 'RPM' in tipo_bruto or 'ATIVO' in tipo_bruto:
                    tipo_final = 'RPM'
                else:
                    tipo_final = 'PA'

                # Salva ou Atualiza no Banco
                obj, created = Produto.objects.update_or_create(
                    sku=sku,
                    defaults={
                        'descricao': descricao,
                        'tipo': tipo_final
                    }
                )
                
                if created: criados += 1
                else: atualizados += 1

            messages.success(request, f"Cadastro Atualizado! {criados} novos, {atualizados} atualizados.")
            
        except Exception as e:
            messages.error(request, f"Erro ao importar produtos: {str(e)}")
            
    return redirect('upload')