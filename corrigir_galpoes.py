import os
import sys
import django

# Configura o Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wms_project.settings')
django.setup()

from core.models import LayoutArmazem

def corrigir_agressivo():
    print("🧹 Iniciando Varredura no Galpão 1...")
    
    # Pega APENAS as ruas que estão no Galpão 1
    ruas_gp1 = LayoutArmazem.objects.filter(gp=1)
    
    movidas = 0
    total = ruas_gp1.count()
    
    print(f"🔍 Analisando {total} ruas que hoje estão no GP 1...")

    for r in ruas_gp1:
        nome = str(r.rua).strip()
        
        # Pula se o nome for vazio
        if not nome or not nome[0].isdigit():
            continue
            
        novo_gp = 1
        
        # Lógica para descobrir o Galpão Correto
        # Se tem 5 digitos (ex: 12005) -> GP 12
        if len(nome) >= 5 and nome[:2].isdigit():
            novo_gp = int(nome[:2])
        # Se tem 4 digitos ou menos (ex: 3017, 7008) -> GP 3, GP 7
        elif nome[0].isdigit():
            novo_gp = int(nome[0])
            
        # Se descobriu que o galpão NÃO deveria ser 1
        if novo_gp != 1 and novo_gp != 0:
            print(f"   🚀 Movendo Rua {nome}: GP 1 -> GP {novo_gp}")
            r.gp = novo_gp
            r.save()
            movidas += 1

    print("-" * 30)
    print(f"✅ FIM! {movidas} ruas foram retiradas do Galpão 1 e corrigidas.")

if __name__ == '__main__':
    corrigir_agressivo()