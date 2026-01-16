from django.contrib import admin
from django.urls import path
from core.views import upload_inventario, dashboard_armazem, radar_fefo

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Rota de Upload
    path('upload/', upload_inventario, name='upload'),
    
    # Rota do Dashboard (Mapa)
    path('dashboard/<int:galpao_id>/', dashboard_armazem, name='dashboard'),
    
    # Rota do Radar FEFO (A LINHA QUE FALTAVA)
    path('fefo/', radar_fefo, name='fefo'),

    # Rota Raiz (Entrada do site)
    path('', upload_inventario), 
]