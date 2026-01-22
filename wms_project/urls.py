from django.contrib import admin
from django.urls import path
from core import views

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
    
    # === OTIMIZAÇÃO / CONSOLIDAÇÃO ===
    path('consolidacao/', views.sugestao_consolidacao, name='consolidacao'),
    
    path('consolidacao/imprimir/', views.relatorio_otimizacao, name='relatorio_otimizacao'),
    
    # para bater com o código que está no HTML ({% url 'realizar_consolidacao' %})
    path('consolidacao/realizar/', views.realizar_consolidacao, name='realizar_consolidacao'),
    
    path('consolidacao/reverter/', views.reverter_consolidacao, name='reverter_consolidacao'),
]