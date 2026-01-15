from django.contrib import admin
from .models import LayoutArmazem, InventarioDiario

@admin.register(LayoutArmazem)
class LayoutAdmin(admin.ModelAdmin):
    list_display = ('rua', 'gp', 'cap_maxima', 'tipo_armazem')
    search_fields = ('rua', 'gp')
    list_filter = ('gp',)

@admin.register(InventarioDiario)
class InventarioAdmin(admin.ModelAdmin):
    list_display = ('data_referencia', 'rua', 'sku', 'quantidade_paletes', 'status')
    list_filter = ('data_referencia', 'status', 'rua__gp') # Filtra por Data e Galpão
    search_fields = ('sku', 'descricao', 'rua__rua')