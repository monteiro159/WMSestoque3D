from django.contrib import admin
from .models import LayoutArmazem, InventarioDiario, Produto

@admin.register(LayoutArmazem)
class LayoutArmazemAdmin(admin.ModelAdmin):
    list_display = ('rua', 'gp', 'cap_maxima', 'tipo_armazem')
    search_fields = ('rua',)
    list_filter = ('gp', 'tipo_armazem')

@admin.register(InventarioDiario)
class InventarioDiarioAdmin(admin.ModelAdmin):
    list_display = ('data_referencia', 'rua', 'sku', 'descricao', 'quantidade_paletes', 'data_validade')
    list_filter = ('data_referencia', 'status')

@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    # AQUI ESTAVA O ERRO: Removemos 'alertar_em' e pusemos as colunas novas
    list_display = ('sku', 'descricao', 'familia', 'tipo', 'shelf_life_dias', 'paletizacao')
    search_fields = ('sku', 'descricao')
    list_filter = ('tipo', 'familia')