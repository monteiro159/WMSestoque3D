import pandas as pd
from datetime import datetime

def processar_excel_estoque(arquivo_excel):
    """
    Lê o Excel de contagem física e retorna um DataFrame limpo e validado.
    """
    # 1. Carregar o arquivo (assumindo que o cabeçalho verde está na linha 1 - index 0)
    try:
        df = pd.read_excel(arquivo_excel, header=0)
    except Exception as e:
        return {"sucesso": False, "erro": f"Erro ao abrir arquivo: {str(e)}"}

    # 2. Mapeamento de Colunas (Excel -> Sistema)
    mapa_colunas = {
        'Endereço': 'endereco_codigo',   # Localização (1001, 1002...)
        'ITEM': 'sku',                   # Código do produto
        'MATERIAL': 'descricao',         # Nome do produto
        'PRODUÇÃO': 'data_producao',     # Data de fabricação
        'STATUS': 'status_estoque',      # Estoque, Bloqueado, etc.
        'POSIÇÃO': 'status_posicao',     # Livre/Bloqueado
        'Quantidade': 'qtd_paletes',     # ATENÇÃO: Estamos rastreando PALETES
        'VALIDADE': 'data_validade',     # Vencimento
        'TIPO': 'tipo_produto',          # PA, RPM, Insumo
        'RNC': 'rnc_codigo',             # Opcional
        'OBSERVAÇÃO': 'observacao'       # Opcional
    }

    # Verifica se todas as colunas obrigatórias existem
    colunas_excel = df.columns.tolist()
    for col_excel in mapa_colunas.keys():
        if col_excel not in colunas_excel:
            return {"sucesso": False, "erro": f"Coluna obrigatória não encontrada: {col_excel}"}

    # Renomeia e mantém apenas as colunas necessárias
    df_final = df[mapa_colunas.keys()].rename(columns=mapa_colunas)

    # 3. Tratamento de Tipos de Dados
    
    # Datas: Converter string '30/12/2025' para objeto Date do Python
    # errors='coerce' transforma datas inválidas em NaT (Not a Time) para não quebrar o script
    df_final['data_producao'] = pd.to_datetime(df_final['data_producao'], dayfirst=True, errors='coerce')
    df_final['data_validade'] = pd.to_datetime(df_final['data_validade'], dayfirst=True, errors='coerce')

    # Números: Garantir que quantidade seja int ou float
    df_final['qtd_paletes'] = pd.to_numeric(df_final['qtd_paletes'], errors='coerce').fillna(0)
    
    # Textos: Limpar espaços em branco extras
    colunas_texto = ['sku', 'descricao', 'status_estoque', 'tipo_produto', 'endereco_codigo']
    for col in colunas_texto:
        df_final[col] = df_final[col].astype(str).str.strip()

    # 4. Regras de Negócio Básicas (Enriquecimento)
    
    # Definindo um ID único para o Lote (já que ignoramos a coluna 'Lote Enchimento')
    # Regra: O Lote será composto por SKU + Data Produção
    df_final['lote_sistema'] = df_final.apply(
        lambda row: f"{row['sku']}_{row['data_producao'].strftime('%Y%m%d')}" 
        if pd.notnull(row['data_producao']) else f"{row['sku']}_INDEF", axis=1
    )

    return {"sucesso": True, "dados": df_final}

# Exemplo de uso (simulação):
# resultado = processar_excel_estoque('seu_arquivo.xlsx')
# if resultado['sucesso']:
#     print(resultado['dados'].head())