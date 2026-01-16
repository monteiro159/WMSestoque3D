from django.db import models

# --- PARTE 1: ESTRUTURA FÍSICA (LAYOUT) ---
class LayoutArmazem(models.Model):
    # Identificadores
    gp = models.IntegerField(verbose_name="Galpão (GP)")
    rua = models.IntegerField(primary_key=True, verbose_name="Código Rua (ID)") 
    
    # Geometria
    largura_colunas = models.IntegerField(verbose_name="Largura (Colunas)")
    base_footprint = models.IntegerField(verbose_name="Base (Chão)")
    
    # Capacidades
    cap_nivel_1 = models.IntegerField(verbose_name="Cap. Nível 1")
    cap_nivel_2 = models.IntegerField(verbose_name="Cap. Nível 2")
    cap_maxima = models.IntegerField(verbose_name="Capacidade Total (N3)")
    
    # Regras
    tipo_armazem = models.CharField(max_length=50, default="COBERTO")
    altura_max_perm = models.IntegerField(default=3)

    class Meta:
        verbose_name = "Layout da Rua"
        verbose_name_plural = "Layouts das Ruas"
        ordering = ['rua']

    def __str__(self):
        return f"Rua {self.rua} (GP {self.gp}) - Cap: {self.cap_maxima}"
    
class Produto(models.Model):
    # Identificação Básica
    sku = models.CharField(max_length=20, primary_key=True, verbose_name="SKU")
    descricao = models.CharField(max_length=200, verbose_name="Produto")
    familia = models.CharField(max_length=100, null=True, blank=True, verbose_name="Família")
    tipo = models.CharField(max_length=50, null=True, blank=True, verbose_name="Tipo") # PA, INSUMO, RPM
    
    # Validade
    shelf_life_dias = models.IntegerField(default=0, verbose_name="Shelf Life (Dias)")
    
    # Dados Logísticos
    unidade_por_pack = models.IntegerField(default=1, verbose_name="Unid/Pack")
    embalagem_geral = models.CharField(max_length=100, null=True, blank=True, verbose_name="Emb. Geral")
    paletizacao = models.IntegerField(default=0, verbose_name="Paletização (Packs/Pal)")
    empilhamento_max = models.IntegerField(default=1, verbose_name="Empilhamento Máx")

    def __str__(self):
        return f"{self.sku} - {self.descricao}"

    class Meta:
        verbose_name = "Cadastro Mestre (Produto)"
        verbose_name_plural = "Cadastro Mestre (Produtos)"

# --- PARTE 2: INVENTÁRIO DIÁRIO (O QUE VEM DO EXCEL) ---
class InventarioDiario(models.Model):
    # Controle de Data e Importação
    data_referencia = models.DateField(verbose_name="Data do Inventário", db_index=True)
    data_importacao = models.DateTimeField(auto_now_add=True)
    
    # Onde está? (Link com o Layout)
    # Se a rua 1001 não existir no Layout, o sistema não deixa salvar (Segurança de Dados)
    rua = models.ForeignKey(LayoutArmazem, on_delete=models.CASCADE, related_name='estoque_atual')
    
    # O que é?
    sku = models.CharField(max_length=20, verbose_name="Item")
    descricao = models.CharField(max_length=200, verbose_name="Material")
    tipo_produto = models.CharField(max_length=10, blank=True, null=True) # PA, RPM...
    
    # Quantidades
    quantidade_paletes = models.FloatField(verbose_name="Qtd Paletes")
    qtd_estoque_un = models.FloatField(verbose_name="Qtd Unidades", null=True, blank=True)
    
    # Validade e Lote
    lote = models.CharField(max_length=50, blank=True, null=True)
    data_producao = models.DateField(null=True, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    
    # Status
    status = models.CharField(max_length=50, default="ESTOQUE") # Bloqueado, Livre...

    class Meta:
        verbose_name = "Registro de Inventário"
        # Garante que não duplique o mesmo produto/lote na mesma rua no mesmo dia
        indexes = [
            models.Index(fields=['data_referencia', 'rua', 'sku']),
        ]

    def __str__(self):
        return f"{self.data_referencia} | Rua {self.rua_id} | SKU {self.sku}"