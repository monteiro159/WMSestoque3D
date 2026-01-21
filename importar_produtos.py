import os
import sys
import django
import pandas as pd

# =============================================================================
# CORREÇÃO DO ERRO DE CAMINHO
# =============================================================================
# Adiciona a pasta atual ao sistema para o Python encontrar o projeto
sys.path.append(os.getcwd())

# Configura o Django para rodar fora do servidor
# ⚠️ ATENÇÃO: Se no seu manage.py estiver 'setup.settings', mude 'wms.settings' para 'setup.settings' aqui abaixo
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wms_project.settings')

try:
    django.setup()
except ModuleNotFoundError:
    # Se der erro de novo, tenta avisar o usuário
    print("❌ ERRO CRÍTICO: Não encontrei a pasta 'wms'.")
    print("Verifique no seu arquivo manage.py qual é o nome do projeto.")
    print("Exemplo: se for 'setup.settings', mude a linha 14 deste script para 'setup.settings'")
    sys.exit(1)

from core.models import Produto

def importar():
    caminho_arquivo = 'produtos.xlsx'
    
    if not os.path.exists(caminho_arquivo):
        print(f"❌ Erro: O arquivo '{caminho_arquivo}' não foi encontrado na pasta raiz.")
        return

    print("📂 Lendo planilha produtos.xlsx...")
    
    try:
        # Lê o Excel
        df = pd.read_excel(caminho_arquivo)
        
        # Limpa nome das colunas (remove espaços e deixa maiúsculo)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        total_lido = len(df)
        criados = 0
        atualizados = 0
        
        print(f"🔄 Processando {total_lido} linhas...")

        for index, row in df.iterrows():
            # Pega SKU (Coluna A) e garante que é string limpa
            raw_sku = row.get('SKU')
            if pd.isna(raw_sku): continue
            
            sku = str(raw_sku).replace('.0', '').strip()
            
            # Pega Descrição (Coluna B)
            descricao = str(row.get('PRODUTO', '')).strip()
            
            # Pega Tipo (Coluna E)
            tipo_bruto = str(row.get('TIPO', 'PA')).upper().strip()
            
            # Normalização rigorosa
            if 'INSUMO' in tipo_bruto:
                tipo_final = 'INSUMO'
            elif 'RPM' in tipo_bruto or 'ATIVO' in tipo_bruto:
                tipo_final = 'RPM'
            else:
                tipo_final = 'PA' # Padrão se for vazio ou qualquer outra coisa

            # Salva no Banco
            obj, created = Produto.objects.update_or_create(
                sku=sku,
                defaults={
                    'descricao': descricao,
                    'tipo': tipo_final
                }
            )

            if created:
                criados += 1
                print(f"   [+] Novo: {sku} -> {tipo_final}")
            else:
                # Se mudou o tipo, avisa (opcional, para não poluir o terminal tirei o print)
                atualizados += 1

        print("-" * 30)
        print(f"✅ Concluído!")
        print(f"📦 Novos SKUs: {criados}")
        print(f"🔄 SKUs Atualizados: {atualizados}")
        print(f"📚 Total na Base: {Produto.objects.count()}")

    except Exception as e:
        print(f"❌ Erro durante a importação: {str(e)}")

if __name__ == '__main__':
    importar()