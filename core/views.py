from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Q, Count, Max, Min
from datetime import date, datetime
import pandas as pd
import unicodedata  # <--- O IMPORT QUE FALTAVA ESTÁ AQUI!

from .models import LayoutArmazem, InventarioDiario, Produto, Cliente

# =============================================================================
# 1. DASHBOARD E MAPA (HOME)
# =============================================================================
def dashboard_armazem(request, galpao_id=0):
    # Filtros Básicos
    filtro_produto = request.GET.get('produto', '').strip()
    filtro_status = request.GET.get('status', '') 
    
    # Pega o último dia de inventário
    ultimo_registro = InventarioDiario.objects.order_by('-data_referencia').first()
    data_ref = ultimo_registro.data_referencia if ultimo_registro else date.today()

    # Base de Ruas (Layout)
    ruas = LayoutArmazem.objects.all().order_by('gp', 'rua')
    if galpao_id > 0:
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
        'galpao': galpao_id,
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
# 2. UPLOAD DE EXCEL (VERSÃO FINAL QUE ACEITA TUDO)
# =============================================================================
def upload_inventario(request):
    if request.method == 'POST' and request.FILES.get('arquivo'):
        arquivo = request.FILES['arquivo']
        
        try:
            df = pd.read_excel(arquivo)
            
            # Limpeza
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
            
            # Validação
            colunas_obrigatorias = ['rua', 'sku', 'descricao']
            faltantes = [col for col in colunas_obrigatorias if col not in df.columns]
            if faltantes:
                messages.error(request, f"Faltando colunas: {', '.join(faltantes)}")
                return redirect('upload')

            # Processamento
            data_hoje = date.today()
            InventarioDiario.objects.filter(data_referencia=data_hoje).delete()
            
            registros = []
            ruas_novas = []

            for index, row in df.iterrows():
                rua_nome = str(row['rua']).strip()
                
                rua_obj, created = LayoutArmazem.objects.get_or_create(
                    rua=rua_nome,
                    defaults={
                        'gp': 1, 'cap_maxima': 100, 'largura_colunas': 1.0, 
                        'base_footprint': 1.0, 'cap_nivel_1': 0, 'cap_nivel_2': 0
                    }
                )
                if created: ruas_novas.append(rua_nome)
                
                validade = row.get('validade')
                if pd.isnull(validade) or str(validade).strip() == '': validade = None
                producao = row.get('producao')
                if pd.isnull(producao) or str(producao).strip() == '': producao = None

                # === NOVA LÓGICA DECIMAL (0 + 3 = 0.3) ===
                
                # 1. Trata a Quantidade (Inteiro)
                try:
                    q_val = row.get('quantidade')
                    qtd_int = int(float(q_val)) if pd.notnull(q_val) and str(q_val).strip() != '' else 0
                except:
                    qtd_int = 0

                # 2. Trata a Fração (Decimal)
                try:
                    f_val = row.get('fracao')
                    fracao_int = int(float(f_val)) if pd.notnull(f_val) and str(f_val).strip() != '' else 0
                except:
                    fracao_int = 0
                
                # 3. Junta os dois visualmente (Ex: 10 e 3 vira 10.3)
                # Se a fração for 0, fica apenas o inteiro (Ex: 10.0)
                # Se a fração for 3, e qtd 0, fica 0.3
                try:
                    str_valor_final = f"{qtd_int}.{fracao_int}"
                    qtd_final = float(str_valor_final)
                except:
                    qtd_final = 0.0

                registros.append(InventarioDiario(
                    data_referencia=data_hoje,
                    rua=rua_obj,
                    sku=str(row['sku']),
                    descricao=row['descricao'],
                    quantidade_paletes=qtd_final, # Agora vai salvo como 0.3
                    data_validade=validade,
                    data_producao=producao,
                    lote=str(row.get('lote', '')),
                    status=str(row.get('status', 'DISPONIVEL'))
                ))
            
            InventarioDiario.objects.bulk_create(registros)
            
            for reg in registros:
                Produto.objects.get_or_create(
                    sku=reg.sku,
                    defaults={'descricao': reg.descricao}
                )

            if ruas_novas:
                qtd_novas = len(ruas_novas)
                exemplo = ", ".join(ruas_novas[:3])
                messages.warning(request, f"⚠️ Atenção: {qtd_novas} novas ruas criadas ({exemplo}).")
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