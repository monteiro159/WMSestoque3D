from django.contrib import admin
from django.urls import path
from core.views import upload_inventario, dashboard_armazem  # <--- IMPORTANTE: Importar dashboard_armazem

urlpatterns = [
    path('admin/', admin.site.urls),
    path('upload/', upload_inventario, name='upload'),
    
    # Rota do Dashboard: Aceita um número inteiro (int) que será o ID do galpão
    path('dashboard/<int:galpao_id>/', dashboard_armazem, name='dashboard'),
    
    # Atalho: Se acessar a raiz (vazio), vai para o upload
    path('', upload_inventario), 
]