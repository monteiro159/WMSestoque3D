import pandas as pd
from core.models import Produto

def importar_base_produtos(arquivo_excel):
    print(f"Lendo base de produtos: {arquivo_excel}...")
    
    try:
        # Lê o Excel
        df = pd.read_excel(arquivo_excel)
        # Remove espaços extras dos nomes das colunas
        df.columns = df.columns.str.strip()
    except Exception as e:
        print(f"Erro ao abrir arquivo: {e}")
        return

    print("Iniciando carga de dados...")
    contador = 0
    erros = 0

    for index, row in df.iterrows():
        try:
            # Pega o SKU e garante que é texto
            sku_val = str(row['SKU']).strip()
            
            # Pega valores numéricos (se vier vazio, poe 0)
            shelf = pd.to_numeric(row.get('SHELF LIFE (DIAS)'), errors='coerce') or 0
            unid_pack = pd.to_numeric(row.get('UNIDADE POR PACK'), errors='coerce') or 1
            palet = pd.to_numeric(row.get('PALETIZAÇÃO'), errors='coerce') or 0
            empil = pd.to_numeric(row.get('EMPILHAMENTO'), errors='coerce') or 1

            # Update or Create: Atualiza se existir, Cria se não existir
            obj, created = Produto.objects.update_or_create(
                sku=sku_val,
                defaults={
                    'descricao': str(row.get('PRODUTO', '')).strip(),
                    'familia': str(row.get('FAMILIA', '')).strip(),
                    'tipo': str(row.get('TIPO', '')).strip(),
                    'shelf_life_dias': int(shelf),
                    'embalagem_geral': str(row.get('EMBALAGEM GERAL', '')).strip(),
                    'unidade_por_pack': int(unid_pack),
                    'paletizacao': int(palet),
                    'empilhamento_max': int(empil)
                }
            )
            contador += 1
            
        except Exception as e:
            print(f"Erro linha {index}: {e}")
            erros += 1
            continue

    print(f"✅ Processo finalizado! {contador} produtos processados. ({erros} erros).")