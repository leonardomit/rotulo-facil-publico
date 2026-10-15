from django.db import models
from django.contrib.auth.models import User


# ---------------------------------------------------------------------------
# Regulatory — versioned lookup tables (NEVER hardcode values in Python code)
# ---------------------------------------------------------------------------

class GrupoPopulacional(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    faixa_etaria_min = models.IntegerField(null=True, blank=True, help_text='Anos (mínimo)')
    faixa_etaria_max = models.IntegerField(null=True, blank=True, help_text='Anos (máximo, None = sem limite)')

    class Meta:
        verbose_name = 'Grupo Populacional'
        verbose_name_plural = 'Grupos Populacionais'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class ListaRegulatoria(models.Model):
    nome = models.CharField(max_length=200)
    versao = models.CharField(max_length=50, help_text='Ex: IN28-2018-v1')
    fonte = models.CharField(max_length=200, help_text='Ex: IN 28/2018 Anexo III')
    vigente = models.BooleanField(
        default=False,
        help_text='Apenas UMA lista pode estar vigente por vez. Marca a lista ativa.'
    )
    data_vigencia = models.DateField()
    observacoes = models.TextField(blank=True)
    lista_idr = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='listas_que_usam_esta_idr',
        help_text=(
            'Lista de onde vêm os valores de IDR para o cálculo de %VD. '
            'A IN 28/2018 define apenas limites — a IDR vem da RDC 269/2005. '
            'Deixe em branco se esta própria lista já contém as IDRs.'
        )
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='listas_criadas')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lista Regulatória'
        verbose_name_plural = 'Listas Regulatórias'
        ordering = ['-data_vigencia']

    def __str__(self):
        vigente_str = ' ✓ VIGENTE' if self.vigente else ''
        return f'{self.nome} [{self.versao}]{vigente_str}'

    def save(self, *args, **kwargs):
        # Ensure only one lista is vigente at a time
        if self.vigente:
            ListaRegulatoria.objects.exclude(pk=self.pk).filter(vigente=True).update(vigente=False)
        super().save(*args, **kwargs)


TIPO_CONSTITUINTE = [
    ('vitamina', 'Vitamina'),
    ('mineral', 'Mineral'),
    ('aminoacido', 'Aminoácido'),
    ('proteina', 'Proteína'),
    ('acido_graxo', 'Ácido Graxo'),
    ('bioativo', 'Substância Bioativa'),
    ('enzima', 'Enzima'),
    ('probiotico', 'Probiótico'),
    ('outro', 'Outro'),
]


class Constituinte(models.Model):
    nome = models.CharField(max_length=400)
    nome_cientifico = models.CharField(max_length=200, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CONSTITUINTE)
    unidade_medida = models.CharField(
        max_length=20,
        help_text='Unidade na qual o valor nutricional é declarado. Ex: mg, mcg, g, UI, UFC'
    )
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='constituintes')
    autorizado = models.BooleanField(default=True)
    anexo_referencia = models.CharField(max_length=100, blank=True,
                                        help_text='Ex: Anexo III — Tabela de IDR')

    class Meta:
        verbose_name = 'Constituinte'
        verbose_name_plural = 'Constituintes'
        ordering = ['tipo', 'nome']

    def __str__(self):
        return f'{self.nome} ({self.get_tipo_display()}) [{self.unidade_medida}]'


class IDR(models.Model):
    """Ingestão Diária de Referência por constituinte e grupo populacional."""
    constituinte = models.ForeignKey(Constituinte, on_delete=models.CASCADE, related_name='idrs')
    grupo_populacional = models.ForeignKey(GrupoPopulacional, on_delete=models.CASCADE,
                                           related_name='idrs')
    valor = models.DecimalField(max_digits=24, decimal_places=4)
    unidade = models.CharField(max_length=20)
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='idrs')

    class Meta:
        verbose_name = 'IDR'
        verbose_name_plural = 'IDRs'
        unique_together = ['constituinte', 'grupo_populacional', 'lista_regulatoria']
        ordering = ['constituinte__nome', 'grupo_populacional__nome']

    def __str__(self):
        return (f'IDR {self.constituinte.nome} / {self.grupo_populacional.nome}: '
                f'{self.valor} {self.unidade}')


class LimiteConstituinte(models.Model):
    """Limites mínimo e máximo por dose para um constituinte num grupo populacional."""
    constituinte = models.ForeignKey(Constituinte, on_delete=models.CASCADE,
                                     related_name='limites')
    grupo_populacional = models.ForeignKey(GrupoPopulacional, on_delete=models.CASCADE,
                                           related_name='limites')
    # max_digits alto para acomodar probióticos em UFC (ex.: 1×10¹⁰ = 10.000.000.000)
    limite_minimo = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    limite_maximo = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    unidade = models.CharField(max_length=20)
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='limites')
    observacoes = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Limite de Constituinte'
        verbose_name_plural = 'Limites de Constituintes'
        ordering = ['constituinte__nome', 'grupo_populacional__nome']

    def __str__(self):
        return (f'Limite {self.constituinte.nome} / {self.grupo_populacional.nome}: '
                f'{self.limite_minimo or "—"}–{self.limite_maximo or "—"} {self.unidade}')


class AlegacaoAutorizada(models.Model):
    constituinte = models.ForeignKey(Constituinte, on_delete=models.CASCADE,
                                     related_name='alegacoes')
    texto_alegacao = models.TextField()
    condicoes = models.TextField(blank=True,
                                  help_text='Condições para uso desta alegação')
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='alegacoes')

    class Meta:
        verbose_name = 'Alegação Autorizada'
        verbose_name_plural = 'Alegações Autorizadas'

    def __str__(self):
        return f'Alegação: {self.constituinte.nome} — {self.texto_alegacao[:60]}…'


# Nutrientes de declaração obrigatória em alimentos (RDC 429/2020 + IN 75/2020)
NUTRIENTES_ALIMENTO = [
    ('energia', 'Valor energético (kcal)'),
    ('carboidratos', 'Carboidratos (g)'),
    ('acucares_totais', 'Açúcares totais (g)'),
    ('acucares_adicionados', 'Açúcares adicionados (g)'),
    ('proteinas', 'Proteínas (g)'),
    ('gorduras_totais', 'Gorduras totais (g)'),
    ('gorduras_saturadas', 'Gorduras saturadas (g)'),
    ('gorduras_trans', 'Gorduras trans (g)'),
    ('fibras', 'Fibras alimentares (g)'),
    ('sodio', 'Sódio (mg)'),
]

NUTRIENTES_ALIMENTO_DICT = dict(NUTRIENTES_ALIMENTO)


class ValorDiarioReferencia(models.Model):
    """
    Valor Diário de referência (VD) para rotulagem nutricional de alimentos,
    conforme IN 75/2020 (dieta de 2.000 kcal). Base para o cálculo de %VD.
    """
    nutriente = models.CharField(max_length=30, choices=NUTRIENTES_ALIMENTO)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    unidade = models.CharField(max_length=10, help_text='Ex: kcal, g, mg')
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='valores_diarios')

    class Meta:
        verbose_name = 'Valor Diário de Referência (Alimentos)'
        verbose_name_plural = 'Valores Diários de Referência (Alimentos)'
        unique_together = ['nutriente', 'lista_regulatoria']
        ordering = ['nutriente']

    def __str__(self):
        return f'VD {self.get_nutriente_display()}: {self.valor} {self.unidade}'


class LimiteLupa(models.Model):
    """
    Limites da rotulagem nutricional frontal (lupa "ALTO EM") da RDC 429/2020.
    Aplicável apenas a ALIMENTOS — suplementos são isentos (RDC 727/2022 Art. 43).
    """
    BASE_CHOICES = [
        ('solido', 'Sólido / semissólido (por 100 g)'),
        ('liquido', 'Líquido (por 100 ml)'),
    ]
    nutriente = models.CharField(
        max_length=30,
        choices=[
            ('acucares_adicionados', 'Açúcar adicionado'),
            ('gorduras_saturadas', 'Gordura saturada'),
            ('sodio', 'Sódio'),
        ],
    )
    base = models.CharField(max_length=10, choices=BASE_CHOICES)
    valor = models.DecimalField(max_digits=12, decimal_places=2,
                                help_text='Limite por 100 g ou 100 ml')
    unidade = models.CharField(max_length=10, help_text='g ou mg')
    rotulo_frontal = models.CharField(
        max_length=100,
        help_text='Texto do selo. Ex: "ALTO EM AÇÚCAR ADICIONADO"'
    )
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='limites_lupa')

    class Meta:
        verbose_name = 'Limite Lupa (Rotulagem Frontal)'
        verbose_name_plural = 'Limites Lupa (Rotulagem Frontal)'
        unique_together = ['nutriente', 'base', 'lista_regulatoria']

    def __str__(self):
        return f'{self.rotulo_frontal}: ≥ {self.valor} {self.unidade}/100{"ml" if self.base == "liquido" else "g"}'


class AdvertenciaObrigatoria(models.Model):
    constituinte = models.ForeignKey(
        Constituinte, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='advertencias',
        help_text='Deixe em branco para advertência geral (não vinculada a constituinte)'
    )
    condicao_texto = models.TextField(
        help_text='Descreva quando esta advertência deve ser disparada. '
                  'Ex: "quando produto contiver fenilalanina"'
    )
    texto_advertencia = models.TextField()
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='advertencias')

    class Meta:
        verbose_name = 'Advertência Obrigatória'
        verbose_name_plural = 'Advertências Obrigatórias'

    def __str__(self):
        alvo = self.constituinte.nome if self.constituinte else 'GERAL'
        return f'Advertência [{alvo}]: {self.texto_advertencia[:60]}…'


class FonteAutorizada(models.Model):
    """
    Forma química / fonte autorizada de um constituinte, conforme a coluna
    "Constituintes Autorizados" da IN 28/2018.

    Ex: "Carbonato de cálcio", "Bisglicinato de ferro", "Acerola em pó".
    Só é permitido usar matéria-prima cuja forma química conste desta lista.
    """
    nome = models.CharField(max_length=400, help_text='Forma química autorizada. Ex: Carbonato de cálcio')
    constituinte = models.ForeignKey(Constituinte, on_delete=models.CASCADE,
                                     related_name='fontes_autorizadas')
    cas = models.CharField(max_length=100, blank=True, help_text='Número CAS')
    categoria = models.CharField(max_length=100, blank=True,
                                 help_text='Categoria ANVISA. Ex: Minerais, Vitaminas')
    funcao = models.TextField(blank=True, help_text='Função declarada na IN 28')
    especificacoes = models.TextField(blank=True, help_text='Farmacopeias/especificações aceitas')
    observacoes = models.TextField(blank=True)
    outras_informacoes = models.TextField(blank=True)
    link_especificacoes = models.URLField(max_length=500, blank=True)
    lista_regulatoria = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                          related_name='fontes_autorizadas')

    class Meta:
        verbose_name = 'Fonte Autorizada'
        verbose_name_plural = 'Fontes Autorizadas'
        ordering = ['constituinte__nome', 'nome']
        unique_together = ['nome', 'constituinte', 'lista_regulatoria']

    def __str__(self):
        return f'{self.nome} → {self.constituinte.nome}'


# ---------------------------------------------------------------------------
# Raw materials
# ---------------------------------------------------------------------------

ALERGENOS_CHOICES = [
    ('gluten', 'Glúten'),
    ('crustaceos', 'Crustáceos'),
    ('ovos', 'Ovos'),
    ('peixe', 'Peixe'),
    ('amendoim', 'Amendoim'),
    ('soja', 'Soja'),
    ('leite', 'Leite'),
    ('castanha_caju', 'Castanha de Caju'),
    ('castanha_para', 'Castanha-do-Pará'),
    ('nozes', 'Nozes'),
    ('amendoas', 'Amêndoas'),
    ('pecas', 'Pecãs'),
    ('pistaches', 'Pistaches'),
    ('macadamia', 'Macadâmia'),
    ('aipo', 'Aipo'),
    ('mostarda', 'Mostarda'),
    ('sesamo', 'Gergelim'),
    ('sulfitos', 'Sulfitos'),
]

ALERGENOS_DICT = dict(ALERGENOS_CHOICES)


class MateriaPrima(models.Model):
    nome_comercial = models.CharField(max_length=200)
    nome_cientifico = models.CharField(max_length=200, blank=True)
    constituinte = models.ForeignKey(
        Constituinte, on_delete=models.PROTECT,
        related_name='materias_primas', null=True, blank=True,
        help_text='Obrigatório para suplementos. Pode ficar vazio para matérias-primas '
                  'de alimentos (ex: maca em pó, gengibre, psyllium).'
    )
    fator_conversao = models.DecimalField(
        max_digits=8, decimal_places=4, default=0,
        help_text='Percentual (%) de nutriente ativo por grama da matéria-prima. '
                  'Ex: 20.0 = 20% de ferro elementar por grama de bisglicinato de ferro. '
                  'Use 0 para matérias-primas apenas de alimentos.'
    )
    unidade_medida = models.CharField(max_length=20, default='g')
    fornecedor = models.CharField(max_length=200, blank=True)
    forma_quimica = models.CharField(max_length=200, blank=True)
    alergenos = models.JSONField(
        default=list,
        help_text='Lista de códigos de alérgenos presentes. Ex: ["gluten", "soja"]'
    )
    transgenico = models.BooleanField(default=False)
    aditivo = models.BooleanField(
        default=False,
        help_text='Marque se esta matéria-prima é um aditivo alimentar'
    )
    funcao_aditivo = models.CharField(
        max_length=200, blank=True,
        help_text='Função tecnológica do aditivo. Ex: Antiumectante'
    )
    ins_aditivo = models.CharField(
        max_length=50, blank=True,
        help_text='Número INS do aditivo. Ex: INS 551'
    )
    ativo = models.BooleanField(default=True)
    observacoes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='materias_criadas')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Matéria-Prima'
        verbose_name_plural = 'Matérias-Primas'
        ordering = ['nome_comercial']

    def __str__(self):
        if self.constituinte:
            return f'{self.nome_comercial} ({self.fator_conversao}% {self.constituinte.nome})'
        return self.nome_comercial

    def alergenos_display(self):
        return [ALERGENOS_DICT.get(a, a) for a in self.alergenos]


class ComposicaoNutricional(models.Model):
    """
    Composição centesimal (por 100 g) de uma matéria-prima — base do cálculo
    da tabela nutricional de ALIMENTOS (RDC 429/2020 + IN 75/2020).
    """
    materia_prima = models.OneToOneField(MateriaPrima, on_delete=models.CASCADE,
                                         related_name='composicao')
    energia_kcal = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='kcal por 100 g. Deixe em branco para calcular por Atwater '
                  '(4 kcal/g carboidratos e proteínas, 9 kcal/g gorduras).'
    )
    carboidratos_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                         verbose_name='Carboidratos (g/100g)')
    acucares_totais_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                            verbose_name='Açúcares totais (g/100g)')
    acucares_adicionados_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                                 verbose_name='Açúcares adicionados (g/100g)')
    proteinas_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                      verbose_name='Proteínas (g/100g)')
    gorduras_totais_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                            verbose_name='Gorduras totais (g/100g)')
    gorduras_saturadas_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                               verbose_name='Gorduras saturadas (g/100g)')
    gorduras_trans_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                           verbose_name='Gorduras trans (g/100g)')
    fibras_g = models.DecimalField(max_digits=8, decimal_places=2, default=0,
                                   verbose_name='Fibras alimentares (g/100g)')
    sodio_mg = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                   verbose_name='Sódio (mg/100g)')
    fonte_dados = models.CharField(
        max_length=200, blank=True,
        help_text='Origem dos dados. Ex: TBCA, TACO, laudo do fornecedor'
    )

    class Meta:
        verbose_name = 'Composição Nutricional (por 100 g)'
        verbose_name_plural = 'Composições Nutricionais (por 100 g)'

    def __str__(self):
        return f'Composição de {self.materia_prima.nome_comercial}'


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

CATEGORIA_PRODUTO = [
    ('suplemento', 'Suplemento Alimentar'),
    ('alimento', 'Alimento'),
]

FORMA_APRESENTACAO = [
    ('capsula', 'Cápsula'),
    ('comprimido', 'Comprimido'),
    ('po', 'Pó'),
    ('liquido', 'Líquido'),
    ('goma', 'Goma'),
    ('sache', 'Sachê'),
    ('barra', 'Barra'),
    ('pastilha', 'Pastilha'),
    ('gel', 'Gel'),
    ('bebida_soluvel', 'Bebida solúvel (pó)'),
    ('shot', 'Shot (líquido)'),
    ('cha', 'Chá / infusão'),
]

# Formas cuja tabela nutricional usa base líquida (por 100 ml) — RDC 429/2020
FORMAS_LIQUIDAS = {'liquido', 'shot'}


class Produto(models.Model):
    nome = models.CharField(max_length=200)
    marca = models.CharField(max_length=200)
    categoria = models.CharField(
        max_length=20, choices=CATEGORIA_PRODUTO, default='suplemento',
        help_text='Suplemento: RDC 243/2018 + IN 28/2018. '
                  'Alimento: RDC 429/2020 + IN 75/2020 (tabela por porção e 100 g/ml, lupa).'
    )
    denominacao_legal = models.CharField(
        max_length=300, blank=True,
        help_text='Denominação legal do alimento. Ex: "Chá verde solúvel em pó". '
                  'Para suplementos é gerada automaticamente se deixada em branco.'
    )
    forma_apresentacao = models.CharField(max_length=20, choices=FORMA_APRESENTACAO)
    peso_unidade_g = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text='Peso líquido de uma unidade em gramas (para formas sólidas)'
    )
    volume_unidade_ml = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True,
        help_text='Volume de uma unidade em mL (para formas líquidas)'
    )
    unidades_por_dose = models.DecimalField(
        max_digits=8, decimal_places=2, default=1,
        help_text='Quantidade de unidades que constitui uma dose. Ex: 2 cápsulas por dose'
    )
    doses_por_embalagem = models.IntegerField()
    medida_caseira = models.CharField(
        max_length=100, blank=True,
        help_text='Ex: "1 scoop (30 g)", "2 cápsulas"'
    )
    grupos_populacionais = models.ManyToManyField(
        GrupoPopulacional, blank=True,
        help_text='Grupos populacionais para os quais o produto se destina '
                  '(obrigatório para suplementos; opcional para alimentos)'
    )
    versao_atual = models.IntegerField(default=1)
    ativo = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='produtos_criados')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Produto'
        verbose_name_plural = 'Produtos'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} — {self.marca} (v{self.versao_atual})'

    @property
    def is_alimento(self):
        return self.categoria == 'alimento'

    @property
    def base_liquida(self):
        """True se a tabela nutricional deve usar base de 100 ml (RDC 429/2020)."""
        if self.forma_apresentacao in FORMAS_LIQUIDAS:
            return True
        return bool(self.volume_unidade_ml) and not self.peso_unidade_g

    @property
    def porcao(self):
        """Tamanho da porção declarada (peso ou volume × unidades por dose)."""
        if self.base_liquida and self.volume_unidade_ml:
            return self.volume_unidade_ml * self.unidades_por_dose, 'ml'
        if self.peso_unidade_g:
            return self.peso_unidade_g * self.unidades_por_dose, 'g'
        return None, None


class FormulacaoItem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='formulacao')
    materia_prima = models.ForeignKey(MateriaPrima, on_delete=models.PROTECT,
                                      related_name='formulacoes')
    quantidade_g = models.DecimalField(
        max_digits=12, decimal_places=6,
        help_text='Quantidade em gramas por UNIDADE do produto (não por dose)'
    )
    overage_pct = models.DecimalField(
        max_digits=6, decimal_places=2, default=0,
        help_text='Sobredosagem de formulação (%). Ex: 10.0 = 10% extra para garantir shelf life'
    )
    ordem = models.IntegerField(default=0, help_text='Ordem de exibição na lista de ingredientes')

    class Meta:
        verbose_name = 'Item de Formulação'
        verbose_name_plural = 'Itens de Formulação'
        ordering = ['ordem']

    def __str__(self):
        return f'{self.materia_prima.nome_comercial}: {self.quantidade_g} g/unidade'


class VersaoProduto(models.Model):
    """Snapshot imutável de uma versão anterior de formulação."""
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='versoes')
    versao_numero = models.IntegerField()
    snapshot_json = models.JSONField()
    motivo = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Versão de Produto'
        verbose_name_plural = 'Versões de Produto'
        ordering = ['-versao_numero']

    def __str__(self):
        return f'{self.produto.nome} v{self.versao_numero} ({self.created_at.date()})'


class CalculoLog(models.Model):
    """Audit log de cada cálculo nutricional realizado."""
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='calculos')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    data_calculo = models.DateTimeField(auto_now_add=True)
    lista_regulatoria_usada = models.ForeignKey(ListaRegulatoria, on_delete=models.PROTECT,
                                                 related_name='calculos')
    resultado_json = models.JSONField()
    grupos_calculados = models.JSONField(default=list)

    class Meta:
        verbose_name = 'Log de Cálculo'
        verbose_name_plural = 'Logs de Cálculo'
        ordering = ['-data_calculo']

    def __str__(self):
        return f'Cálculo {self.produto.nome} em {self.data_calculo.strftime("%d/%m/%Y %H:%M")}'
