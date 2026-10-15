from django.urls import path
from . import views

app_name = 'rotulagem'

urlpatterns = [
    # Diagnóstico / operação
    path('healthz/', views.healthz, name='healthz'),
    path('healthz/criar-usuario/', views.criar_usuario, name='criar_usuario'),

    # Dashboard
    path('', views.DashboardView.as_view(), name='dashboard'),

    # Produtos
    path('produtos/', views.ProdutoListView.as_view(), name='produto_list'),
    path('produtos/novo/', views.ProdutoCreateView.as_view(), name='produto_create'),
    path('produtos/<int:pk>/', views.ProdutoDetailView.as_view(), name='produto_detail'),
    path('produtos/<int:pk>/editar/', views.ProdutoUpdateView.as_view(), name='produto_update'),
    path('produtos/<int:pk>/formulacao/', views.ProdutoFormulacaoView.as_view(), name='produto_formulacao'),
    path('produtos/<int:pk>/calculo/', views.ProdutoCalculoView.as_view(), name='produto_calculo'),
    path('produtos/<int:pk>/relatorio/', views.ProdutoRelatorioView.as_view(), name='produto_relatorio'),
    path('produtos/<int:pk>/rotulo/', views.ProdutoRotuloView.as_view(), name='produto_rotulo'),
    path('produtos/<int:pk>/imprimir/', views.ProdutoImprimirView.as_view(), name='produto_imprimir'),
    path('produtos/<int:pk>/pdf/', views.ProdutoExportarPDFView.as_view(), name='produto_pdf'),

    # HTMX — formulação
    path('produtos/<int:produto_pk>/formulacao/add/', views.FormulacaoItemAddView.as_view(), name='formulacao_add'),
    path('formulacao/<int:pk>/delete/', views.FormulacaoItemDeleteView.as_view(), name='formulacao_delete'),

    # HTMX — utilities
    path('nutriente-info/', views.NutrienteInfoView.as_view(), name='nutriente_info'),

    # Matérias-Primas
    path('materias-primas/', views.MateriaPrimaListView.as_view(), name='materia_prima_list'),
    path('materias-primas/nova/', views.MateriaPrimaCreateView.as_view(), name='materia_prima_create'),
    path('materias-primas/<int:pk>/editar/', views.MateriaPrimaUpdateView.as_view(), name='materia_prima_update'),

    # Constituintes
    path('constituintes/', views.ConstituinteListView.as_view(), name='constituinte_list'),
]
