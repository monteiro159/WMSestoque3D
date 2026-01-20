import os
import django
import pandas as pd

# 1. Configuração do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wms_project.settings')
django.setup()

from core.models import LayoutArmazem

def importar_layout():
    caminho_csv = 'layout_armazem.csv'
    print(f"Lendo arquivo: {caminho_csv}...")
    
    try:
        df = pd.read_csv(caminho_csv, sep=';', encoding='utf-8-sig')
        df.columns = df.columns.str.strip()
        
        contador_novos = 0
        contador_atualizados = 0

        print("Iniciando processamento no Banco de Dados...")

        for index, row in df.iterrows():
            try:
                def tratar_numero(valor):
                    return float(str(valor).replace(',', '.'))

                largura = tratar_numero(row['Coluna'])
                footprint = tratar_numero(row['base foot_print'])
                
                # Pegamos as capacidades do CSV
                cap1 = int(row['TOTAL 1 ALTURA'])
                cap2 = int(row['TOTAL 2 ALTURA'])
                # cap3 = int(row['TOTAL 3 ALTURA']) # Ignoramos pois o banco não tem o campo
                
                # Calculamos o total (mesmo que o banco não salve o nível 3 separado,
                # podemos somar ele no total geral se quiser, ou ignorar)
                # Vamos somar apenas o que cabe nos niveis existentes
                total_capacidade = cap1 + cap2 

                obj, created = LayoutArmazem.objects.update_or_create(
                    rua=str(row['RUA']),
                    defaults={
                        'gp': int(row['GP']),
                        'largura_colunas': largura,
                        'base_footprint': footprint,
                        
                        'cap_nivel_1': cap1,
                        'cap_nivel_2': cap2,
                        # 'cap_nivel_3': cap3, <--- REMOVIDO
                        
                        'cap_maxima': total_capacidade,
                        'tipo_armazem': row['TIPO ARMAZEM'],
                        
                        # 'nivel': 1, <--- REMOVIDO
                        'altura_galpao': 10.0,
                        'profundidade_longarinas': 1.0
                    }
                )

                if created: contador_novos += 1
                else: contador_atualizados += 1

            except KeyError as e:
                print(f"Erro na linha {index}: Coluna {e} não encontrada.")
            except Exception as e:
                print(f"Erro genérico na linha {index}: {e}")

        print(f"CONCLUÍDO! Criados: {contador_novos} | Atualizados: {contador_atualizados}")

    except FileNotFoundError:
        print(f"ERRO: Arquivo '{caminho_csv}' não encontrado.")
    except Exception as e:
        print(f"ERRO CRÍTICO: {e}")

if __name__ == '__main__':
    importar_layout()