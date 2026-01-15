import pandas as pd
from datetime import date
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Sum, Count
from .forms import UploadInventarioForm
from .models import InventarioDiario, LayoutArmazem

# --- PARTE 1: UPLOAD ---
def upload_inventario(request):
    if request.method == "POST":
        form = UploadInventarioForm(request.POST, request.FILES)
        if form.is_valid():
            arquivo = request.FILES['arquivo_excel']
            data_ref = form.cleaned_data['data_do_inventario']
            
            try:
                df = pd.read_excel(arquivo)
                df.columns = df.columns.str.strip()
                
                if 'Endereço' not in df.columns:
                    messages.error(request, "Coluna 'Endereço' não encontrada.")
                    return redirect('upload')

                objetos_para_salvar = []
                
                for index, row in df.iterrows():
                    try:
                        cod_rua = int(row['Endereço'])
                        rua_obj = LayoutArmazem.objects.filter(rua=cod_rua).first()
                        if not rua_obj: continue 

                        # Tratamento de Datas
                        d_prod = pd.to_datetime(row.get('PRODUÇÃO'), dayfirst=True, errors='coerce')
                        if pd.isna(d_prod): d_prod = None
                        d_val = pd.to_datetime(row.get('VALIDADE'), dayfirst=True, errors='coerce')
                        if pd.isna(d_val): d_val = None
                        
                        sku = str(row.get('ITEM', '')).strip()
                        lote = f"{sku}_{d_prod.strftime('%Y%m%d')}" if d_prod else f"{sku}_ND"

                        obj = InventarioDiario(
                            data_referencia=data_ref,
                            rua=rua_obj,
                            sku=sku,
                            descricao=str(row.get('MATERIAL', '')).strip(),
                            quantidade_paletes=float(row.get('Quantidade', 0)) if pd.notnull(row.get('Quantidade')) else 0,
                            status=str(row.get('STATUS', 'ESTOQUE')),
                            tipo_produto=str(row.get('TIPO', '')),
                            data_validade=d_val,
                            data_producao=d_prod,
                            lote=lote
                        )
                        objetos_para_salvar.append(obj)
                    except: continue

                if objetos_para_salvar:
                    InventarioDiario.objects.filter(data_referencia=data_ref).delete()
                    InventarioDiario.objects.bulk_create(objetos_para_salvar)
                    messages.success(request, f"Sucesso! {len(objetos_para_salvar)} registros.")
                    return redirect('dashboard', galpao_id=1)
                
            except Exception as e:
                messages.error(request, f"Erro: {e}")
                return redirect('upload')
    else:
        form = UploadInventarioForm()
    return render(request, 'core/upload.html', {'form': form})

# --- PARTE 2: DASHBOARD (COM A CORREÇÃO DOS BOTÕES) ---
def dashboard_armazem(request, galpao_id=1):
    filtro_produto = request.GET.get('produto', '').strip().lower()
    filtro_status = request.GET.get('status', '')

    # 1. Lista de Galpões
    galpoes_existentes = LayoutArmazem.objects.values_list('gp', flat=True).distinct().order_by('gp')
    
    # 2. Dados de Referência
    ultimo = InventarioDiario.objects.order_by('-data_referencia').first()
    data_ref = ultimo.data_referencia if ultimo else date.today()

    # --- LÓGICA DE "INSIGHTS" (Estatísticas Gerais) ---
    # Pega todos os itens da data atual
    todos_itens = InventarioDiario.objects.filter(data_referencia=data_ref)
    
    # Agrupa por descrição e soma quantidade
    stats_produtos = todos_itens.values('descricao').annotate(total=Sum('quantidade_paletes')).order_by('-total')
    
    top_produto = stats_produtos.first() # O que mais tem
    bottom_produto = stats_produtos.last() # O que menos tem (mas tem algo)
    total_paletes_geral = todos_itens.aggregate(Sum('quantidade_paletes'))['quantidade_paletes__sum'] or 0

    # --- LÓGICA DO MAPA ---
    mapa_ruas = []
    
    # Se galpao_id for 0, mostra TODOS (Visão Geral)
    # ATENÇÃO: Se tiver muitas ruas, isso pode ficar pesado. O ideal para "Todos" seria um resumo.
    # Mas vou fazer mostrar tudo conforme seu pedido de "selecionar todos".
    if galpao_id == 0:
        ruas = LayoutArmazem.objects.all().order_by('gp', 'rua')
        titulo_galpao = "Visão Global (Todos os Galpões)"
    else:
        ruas = LayoutArmazem.objects.filter(gp=galpao_id).order_by('rua')
        titulo_galpao = f"Galpão {galpao_id}"

    # Otimização: Buscar todos os estoques de uma vez para não fazer 1000 consultas no banco
    # Cria um dicionário: { id_rua: qtd_paletes }
    estoques_dict = dict(InventarioDiario.objects.filter(
        data_referencia=data_ref
    ).values_list('rua_id').annotate(total=Sum('quantidade_paletes')).values_list('rua_id', 'total'))

    # Cria dicionário de produtos: { id_rua: nome_produto }
    # Pega apenas o primeiro produto de cada rua para exibir
    produtos_dict = {}
    itens_raw = InventarioDiario.objects.filter(data_referencia=data_ref).values('rua_id', 'descricao')
    for item in itens_raw:
        if item['rua_id'] not in produtos_dict:
            produtos_dict[item['rua_id']] = item['descricao']

    for rua in ruas:
        ocupacao = estoques_dict.get(rua.rua, 0)
        produto = produtos_dict.get(rua.rua, "-")
        
        pct = int((ocupacao / rua.cap_maxima) * 100) if rua.cap_maxima > 0 else 0
        
        cor = "bg-emerald-600/20 border-emerald-500/50 text-emerald-100" # Livre Moderno
        bar_color = "bg-emerald-500"
        
        if pct > 70: 
            cor = "bg-amber-600/20 border-amber-500/50 text-amber-100"
            bar_color = "bg-amber-500"
        if pct >= 95: 
            cor = "bg-rose-600/20 border-rose-500/50 text-rose-100"
            bar_color = "bg-rose-500"
        if ocupacao == 0: 
            cor = "bg-slate-800/50 border-slate-700/50 text-slate-500"
            bar_color = "bg-slate-600"

        # Filtros
        if filtro_produto and filtro_produto not in produto.lower(): continue
        if filtro_status == 'vazia' and ocupacao > 0: continue
        if filtro_status == 'cheia' and pct < 95: continue

        mapa_ruas.append({
            'codigo': rua.rua,
            'gp': rua.gp, # Importante para saber de qual galpão é na visão geral
            'ocupacao': int(ocupacao),
            'capacidade': rua.cap_maxima,
            'porcentagem': pct,
            'cor_bg': cor,
            'cor_bar': bar_color,
            'produto': produto
        })

    return render(request, 'core/dashboard.html', {
        'galpao': galpao_id,
        'titulo_galpao': titulo_galpao,
        'data_ref': data_ref,
        'mapa': mapa_ruas,
        'filtro_produto': filtro_produto,
        'filtro_status': filtro_status,
        'lista_galpoes': galpoes_existentes,
        # Insights
        'top_produto': top_produto,
        'bottom_produto': bottom_produto,
        'total_geral': total_paletes_geral
    })