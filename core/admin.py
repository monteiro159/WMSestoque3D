from django.contrib import admin
from .models import LayoutArmazem, InventarioDiario, Produto, Cliente

# Configuração do Layout do Armazém
@admin.register(LayoutArmazem)
class LayoutArmazemAdmin(admin.ModelAdmin):
    # REMOVIDO 'nivel' PARA CORRIGIR O ERRO
    list_display = ('rua', 'gp', 'cap_maxima') 
    list_filter = ('gp',)
    search_fields = ('rua',)

# Configuração do Produto (Cadastro Mestre)
@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ('sku', 'descricao', 'tipo', 'shelf_life_dias')
    list_filter = ('tipo',)
    search_fields = ('sku', 'descricao')

# Configuração do Inventário
@admin.register(InventarioDiario)
class InventarioDiarioAdmin(admin.ModelAdmin):
    list_display = ('data_referencia', 'rua', 'sku', 'descricao', 'quantidade_paletes', 'data_validade')
    list_filter = ('data_referencia', 'status')
    search_fields = ('sku', 'descricao', 'lote')

# Configuração do Cliente (SLA)
@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo_restricao', 'valor_restricao')
    search_fields = ('nome',)