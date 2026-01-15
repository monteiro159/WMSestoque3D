import pandas as pd
from core.models import LayoutArmazem

def importar_layout_inicial(caminho_do_csv):
    """
    Lê o CSV de dados e popula o banco de dados.
    """
    # ATENÇÃO: sep=';' define que estamos usando ponto-e-vírgula como separador
    try:
        df = pd.read_csv(caminho_do_csv, sep=';')
    except Exception as e:
        print(f"Erro ao ler arquivo: {e}")
        return

    # Limpa espaços em branco nos nomes das colunas (ex: " RUA " vira "RUA")
    df.columns = df.columns.str.strip()

    objetos_para_criar = []
    
    print("Iniciando importação...")

    for index, row in df.iterrows():
        try:
            obj = LayoutArmazem(
                gp=row['GP'],
                rua=row['RUA'],
                largura_colunas=row['Coluna'],
                base_footprint=row['base foot_print'],
                cap_nivel_1=row['TOTAL 1 ALTURA'],
                cap_nivel_2=row['TOTAL 2 ALTURA'],
                cap_maxima=row['TOTAL 3 ALTURA'],
                tipo_armazem=row['TIPO ARMAZEM'],
                altura_max_perm=row['ALTURA_MAX']
            )
            objetos_para_criar.append(obj)
        except KeyError as e:
            print(f"Erro na linha {index}: Coluna {e} não encontrada.")
            return

    # Salva no banco
    LayoutArmazem.objects.bulk_create(objetos_para_criar, ignore_conflicts=True)
    print(f"Sucesso! {len(objetos_para_criar)} ruas cadastradas.")