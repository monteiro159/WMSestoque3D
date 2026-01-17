from django.contrib import admin
from django.urls import path
from core import views  # <--- O JEITO CERTO (Importa o arquivo todo)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Dashboard
    path('', views.dashboard_armazem, name='home'),
    path('dashboard/<int:galpao_id>/', views.dashboard_armazem, name='dashboard'),

    # Upload
    path('upload/', views.upload_inventario, name='upload'),

    # Relatórios
    path('fefo/', views.radar_fefo, name='fefo'),

    # Operação (Picking)
    path('picking/', views.picking_busca, name='picking'),
    
    path('consolidacao/', views.sugestao_consolidacao, name='consolidacao'),
]