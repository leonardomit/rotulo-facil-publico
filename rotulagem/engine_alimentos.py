"""
Motor de Cálculo Nutricional de ALIMENTOS — Rótulo Fácil
=========================================================
Implementa a rotulagem nutricional de alimentos embalados conforme
RDC 429/2020 e IN 75/2020:

- Tabela nutricional com dupla declaração: por 100 g (ou 100 ml) e por porção;
- %VD calculado sobre os Valores Diários de referência (dieta de 2.000 kcal);
- Regras de arredondamento e valores "não significativos" (IN 75/2020);
- Rotulagem nutricional frontal — lupa "ALTO EM" (RDC 429/2020).

Os Valores Diários (VD) e os limites da lupa são lidos do banco de dados
(ValorDiarioReferencia / LimiteLupa) — jamais hardcoded.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .models import (
    Produto, ListaRegulatoria, ValorDiarioReferencia, LimiteLupa,
    NUTRIENTES_ALIMENTO,
)

# (código, campo em ComposicaoNutricional, unidade declarada)
_CAMPOS_NUTRIENTES = [
    ('energia', 'energia_kcal', 'kcal'),
    ('carboidratos', 'carboidratos_g', 'g'),
    ('acucares_totais', 'acucares_totais_g', 'g'),
    ('acucares_adicionados', 'acucares_adicionados_g', 'g'),
    ('proteinas', 'proteinas_g', 'g'),
    ('gorduras_totais', 'gorduras_totais_g', 'g'),
    ('gorduras_saturadas', 'gorduras_saturadas_g', 'g'),
    ('gorduras_trans', 'gorduras_trans_g', 'g'),
    ('fibras', 'fibras_g', 'g'),
    ('sodio', 'sodio_mg', 'mg'),
]

_NOMES = dict(NUTRIENTES_ALIMENTO)


def localizar_lista_alimentos(lista: Optional[ListaRegulatoria] = None) -> ListaRegulatoria:
    """
    Localiza a lista regulatória de alimentos: aquela que possui Valores
    Diários de Referência cadastrados. Não usa o flag ``vigente`` para não
    conflitar com a lista vigente de suplementos (IN 28/2018).
    """
    if lista is not None:
        return lista
    lista = (
        ListaRegulatoria.objects
        .filter(valores_diarios__isnull=False)
        .distinct()
        .order_by('-data_vigencia')
        .first()
    )
    if lista is None:
        raise ValueError(
            'Nenhuma lista regulatória de alimentos encontrada. '
            'Execute: python manage.py seed_alimentos_rdc429'
        )
    return lista


class MotorCalculoAlimento:
    """
    Calcula a tabela nutricional de um produto da categoria ALIMENTO a partir
    da composição centesimal (por 100 g) das matérias-primas da formulação.

    Uso::

        motor = MotorCalculoAlimento(produto)
        resultado = motor.calcular()
        # resultado['nutrientes'] → lista na ordem obrigatória da IN 75/2020
        # resultado['lupa'] → selos "ALTO EM" aplicáveis
    """

    def __init__(self, produto: Produto, lista_regulatoria: Optional[ListaRegulatoria] = None):
        self.produto = produto
        self.lista = localizar_lista_alimentos(lista_regulatoria)
        self._resultado: Optional[dict] = None

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def calcular(self) -> dict:
        porcao_valor, porcao_unidade = self.produto.porcao
        if not porcao_valor:
            raise ValueError(
                'Defina o peso (g) ou volume (ml) da unidade do produto para '
                'calcular a tabela nutricional de alimento.'
            )

        avisos = []
        totais_porcao = {codigo: Decimal('0') for codigo, _, _ in _CAMPOS_NUTRIENTES}
        detalhes_mp = []

        formulacao = self.produto.formulacao.select_related('materia_prima')
        for item in formulacao:
            mp = item.materia_prima
            massa_por_porcao = (
                item.quantidade_g
                * self.produto.unidades_por_dose
                * (Decimal('1') + item.overage_pct / Decimal('100'))
            )

            composicao = getattr(mp, 'composicao', None)
            if composicao is None:
                avisos.append(
                    f'Matéria-prima "{mp.nome_comercial}" sem composição nutricional '
                    'cadastrada — contribuição considerada zero. Cadastre a composição '
                    'centesimal (por 100 g) na tela de matérias-primas.'
                )
                detalhes_mp.append({
                    'materia_prima': mp.nome_comercial,
                    'massa_por_porcao_g': float(massa_por_porcao),
                    'tem_composicao': False,
                })
                continue

            contribuicao = {}
            for codigo, campo, _unid in _CAMPOS_NUTRIENTES:
                if codigo == 'energia':
                    continue
                valor_100g = getattr(composicao, campo) or Decimal('0')
                contribuicao[codigo] = massa_por_porcao * valor_100g / Decimal('100')
                totais_porcao[codigo] += contribuicao[codigo]

            # Energia: valor informado ou fatores de Atwater (4/4/9)
            if composicao.energia_kcal is not None:
                energia = massa_por_porcao * composicao.energia_kcal / Decimal('100')
                origem_energia = 'informada (por 100 g)'
            else:
                energia = (
                    contribuicao['carboidratos'] * 4
                    + contribuicao['proteinas'] * 4
                    + contribuicao['gorduras_totais'] * 9
                )
                origem_energia = 'Atwater (carb ×4 + prot ×4 + gord ×9)'
            totais_porcao['energia'] += energia

            detalhes_mp.append({
                'materia_prima': mp.nome_comercial,
                'massa_por_porcao_g': float(massa_por_porcao),
                'tem_composicao': True,
                'origem_energia': origem_energia,
                'contribuicao_energia_kcal': float(energia),
            })

        # Base de 100 g / 100 ml
        base_liquida = self.produto.base_liquida
        base_label = '100 ml' if base_liquida else '100 g'
        fator_100 = Decimal('100') / porcao_valor

        vds = {vd.nutriente: vd for vd in self.lista.valores_diarios.all()}

        nutrientes = []
        for codigo, _campo, unidade in _CAMPOS_NUTRIENTES:
            por_porcao = totais_porcao[codigo]
            por_100 = por_porcao * fator_100

            vd = vds.get(codigo)
            if vd and vd.valor:
                pct_vd = (por_porcao / vd.valor * Decimal('100')).quantize(
                    Decimal('1'), rounding=ROUND_HALF_UP
                )
            else:
                pct_vd = None  # Ex: açúcares totais e gorduras trans não têm VD

            valor_porcao_decl, regra = self._arredondar(codigo, por_porcao)
            valor_100_decl, _ = self._arredondar(codigo, por_100)

            nutrientes.append({
                'codigo': codigo,
                'nome': _NOMES[codigo],
                'unidade': unidade,
                'por_100': float(valor_100_decl),
                'por_porcao': float(valor_porcao_decl),
                'pct_vd': float(pct_vd) if pct_vd is not None else None,
                'vd_referencia': float(vd.valor) if vd else None,
                'valor_bruto_porcao': float(por_porcao),
                'regra_arredondamento': regra,
            })

        self._resultado = {
            'porcao': {
                'valor': float(porcao_valor),
                'unidade': porcao_unidade,
                'medida_caseira': self.produto.medida_caseira,
                'porcoes_por_embalagem': self.produto.doses_por_embalagem,
            },
            'base': base_label,
            'base_liquida': base_liquida,
            'nutrientes': nutrientes,
            'lupa': self._avaliar_lupa(totais_porcao, fator_100, base_liquida),
            'avisos': avisos,
            'detalhes_materias_primas': detalhes_mp,
            'lista_regulatoria': {
                'id': self.lista.id,
                'versao': self.lista.versao,
                'fonte': self.lista.fonte,
            },
        }
        return self._resultado

    # ------------------------------------------------------------------
    # Lupa "ALTO EM" — RDC 429/2020
    # ------------------------------------------------------------------

    def _avaliar_lupa(self, totais_porcao: dict, fator_100: Decimal,
                      base_liquida: bool) -> dict:
        base = 'liquido' if base_liquida else 'solido'
        limites = self.lista.limites_lupa.filter(base=base)

        selos = []
        analise = []
        for limite in limites:
            valor_100 = totais_porcao.get(limite.nutriente, Decimal('0')) * fator_100
            atingido = valor_100 >= limite.valor
            if atingido:
                selos.append(limite.rotulo_frontal)
            analise.append({
                'nutriente': _NOMES.get(limite.nutriente, limite.nutriente),
                'valor_por_100': float(valor_100.quantize(Decimal('0.01'))),
                'limite': float(limite.valor),
                'unidade': limite.unidade,
                'atingido': atingido,
            })

        return {
            'aplicavel': True,
            'selos': selos,
            'analise': analise,
            'referencia': 'RDC 429/2020 — rotulagem nutricional frontal',
        }

    # ------------------------------------------------------------------
    # Arredondamento e valores não significativos — IN 75/2020
    # ------------------------------------------------------------------

    def _arredondar(self, codigo: str, valor: Decimal) -> tuple[Decimal, str]:
        """
        Regras da IN 75/2020 (simplificadas):
        - Energia: < 4 kcal → 0; demais, inteiro.
        - Gordura trans: < 0,1 g → 0.
        - Demais em g: < 0,5 g → 0; < 10 g → 1 casa decimal; ≥ 10 g → inteiro.
        - Sódio (mg): < 5 mg → 0; demais, inteiro.
        """
        if codigo == 'energia':
            if valor < 4:
                return Decimal('0'), 'Energia < 4 kcal → não significativo (0)'
            arred = valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            return arred, f'Energia arredondada para inteiro → {arred} kcal'

        if codigo == 'sodio':
            if valor < 5:
                return Decimal('0'), 'Sódio < 5 mg → não significativo (0)'
            arred = valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            return arred, f'Sódio arredondado para inteiro → {arred} mg'

        if codigo == 'gorduras_trans':
            if valor < Decimal('0.1'):
                return Decimal('0'), 'Gordura trans < 0,1 g → não significativo (0)'

        if valor < Decimal('0.5'):
            return Decimal('0'), f'{_NOMES[codigo]} < 0,5 g → não significativo (0)'
        if valor < 10:
            arred = valor.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
            return arred, f'< 10 g → 1 casa decimal → {arred} g'
        arred = valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return arred, f'≥ 10 g → inteiro → {arred} g'
