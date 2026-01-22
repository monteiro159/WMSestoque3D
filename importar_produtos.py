import os
import sys
import django
import pandas as pd

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wms_project.settings')

try:
    django.setup()
except ModuleNotFoundError:
    print("❌ ERRO: Verifique o nome do projeto no manage.py")
    sys.exit(1)

from core.models import Produto

def importar():
    caminho_arquivo = 'produtos.xlsx'
    if not os.path.exists(caminho_arquivo):
        print("❌ Arquivo produtos.xlsx não encontrado.")
        return

    print("📂 Lendo produtos.xlsx (Lendo Empilhamento)...")
    
    try:
        df = pd.read_excel(caminho_arquivo)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        criados = 0
        atualizados = 0

        for index, row in df.iterrows():
            raw_sku = row.get('SKU')
            if pd.isna(raw_sku): continue
            
            sku = str(raw_sku).replace('.0', '').strip()
            descricao = str(row.get('PRODUTO', '')).strip()
            tipo_bruto = str(row.get('TIPO', 'PA')).upper().strip()
            
            # Lê o Empilhamento (Coluna I) - Padrão é 1 se estiver vazio
            try:
                empilhamento = int(float(row.get('EMPILHAMENTO', 1)))
            except:
                empilhamento = 1
            
            # Normalização do Tipo
            if 'INSUMO' in tipo_bruto: tipo_final = 'INSUMO'
            elif 'RPM' in tipo_bruto or 'ATIVO' in tipo_bruto: tipo_final = 'RPM'
            else: tipo_final = 'PA'

            obj, created = Produto.objects.update_or_create(
                sku=sku,
                defaults={
                    'descricao': descricao,
                    'tipo': tipo_final,
                    'empilhamento': empilhamento # Atualiza o empilhamento
                }
            )

            if created: criados += 1
            else: atualizados += 1

        print("-" * 30)
        print(f"✅ Sucesso! Base de Produtos Atualizada.")
        print(f"📦 Novos: {criados} | 🔄 Atualizados: {atualizados}")

    except Exception as e:
        print(f"❌ Erro: {str(e)}")

if __name__ == '__main__':
    importar()