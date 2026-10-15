"""
Motor de Cálculo Nutricional — Rótulo Fácil Suplementos
========================================================
Implementa o cálculo de nutrientes por dose conforme RDC 243/2018, IN 28/2018
e demais normativas vigentes. Todos os valores regulatórios (IDR, limites) são
lidos do banco de dados — jamais hardcoded.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from django.db import models as dj_models
from .models import (
    Produto, GrupoPopulacional, ListaRegulatoria,
    IDR, LimiteConstituinte, AdvertenciaObrigatoria, Constituinte,
)


class MotorCalculo:
    """
    Calcula os valores nutricionais declaráveis por dose para um produto.

    Uso básico::

        from rotulagem.engine import MotorCalculo
        from rotulagem.models import Produto, GrupoPopulacional

        produto = Produto.objects.get(pk=1)
        grupo = GrupoPopulacional.objects.get(nome='Adultos (19-59 anos)')
        motor = MotorCalculo(produto, grupo)
        resultado = motor.calcular_por_dose()
        violacoes = motor.validar_conformidade()
        advertencias = motor.gerar_advertencias()
    """

    def __init__(
        self,
        produto: Produto,
        grupo_populacional: GrupoPopulacional,
        lista_regulatoria: Optional[ListaRegulatoria] = None,
    ):
        self.produto = produto
        self.grupo = grupo_populacional
        try:
            self.lista = lista_regulatoria or ListaRegulatoria.objects.get(vigente=True)
        except ListaRegulatoria.DoesNotExist:
            raise ValueError(
                'Nenhuma Lista Regulatória marcada como vigente. '
                'Acesse o Admin e marque uma lista como vigente.'
            )
        self._resultado: Optional[dict] = None

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------

    def calcular_por_dose(self) -> dict:
        """
        Retorna dicionário {nome_constituinte: {...dados...}} com os valores
        calculados e audit trail completo de cada etapa.
        """
        resultado = {}

        formulacao = self.produto.formulacao.select_related(
            'materia_prima__constituinte'
        )

        for item in formulacao:
            mp = item.materia_prima
            c = mp.constituinte
            if c is None:
                # MP sem constituinte (cadastrada para alimentos) — não entra
                # na tabela nutricional de suplementos
                continue

            # Passo 1 — quantidade por dose (unidades × qtde por unidade)
            qtde_por_dose = item.quantidade_g * self.produto.unidades_por_dose

            # Passo 2 — aplicar overage (sobredosagem de formulação)
            fator_overage = Decimal('1') + (item.overage_pct / Decimal('100'))
            qtde_com_overage = qtde_por_dose * fator_overage

            # Passo 3 — extrair nutriente ativo usando fator de conversão
            # fator_conversao é % em g/g (ex: 100% = 1g nutriente puro por 1g MP)
            # O resultado está em gramas; converte para a unidade declarada do constituinte.
            nutriente_ativo_g = qtde_com_overage * (mp.fator_conversao / Decimal('100'))
            fator_conversao_unidade, descricao_unidade = self._converter_unidade(c.unidade_medida)
            nutriente_ativo = nutriente_ativo_g * fator_conversao_unidade

            # Passo 4 — buscar IDR e calcular %VD
            idr = self._buscar_idr(c)
            if idr:
                pct_vd = (nutriente_ativo / idr.valor * Decimal('100')).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
            else:
                pct_vd = None

            # Passo 5 — arredondamento conforme regras ANVISA
            valor_arredondado, regra_arredondamento = self._arredondar(nutriente_ativo, c)

            resultado[c.nome] = {
                'constituinte_id': c.id,
                'tipo': c.tipo,
                'tipo_display': c.get_tipo_display(),
                'valor_declarado': float(valor_arredondado),
                'unidade': c.unidade_medida,
                'pct_vd': float(pct_vd) if pct_vd is not None else None,
                'idr_valor': float(idr.valor) if idr else None,
                'idr_unidade': idr.unidade if idr else None,
                'materia_prima': mp.nome_comercial,
                'audit_trail': {
                    'quantidade_por_unidade_g': float(item.quantidade_g),
                    'unidades_por_dose': float(self.produto.unidades_por_dose),
                    'passo_1_qtde_por_dose': (
                        f'{item.quantidade_g} g × {self.produto.unidades_por_dose} unidades'
                        f' = {qtde_por_dose} g'
                    ),
                    'overage_pct': float(item.overage_pct),
                    'passo_2_com_overage': (
                        f'{qtde_por_dose} g × (1 + {item.overage_pct}/100)'
                        f' = {qtde_com_overage} g'
                    ),
                    'fator_conversao_pct': float(mp.fator_conversao),
                    'passo_3_nutriente_ativo': (
                        f'{qtde_com_overage} g × {mp.fator_conversao}/100'
                        f' = {nutriente_ativo_g} g → {descricao_unidade}'
                        f' → {nutriente_ativo} {c.unidade_medida}'
                    ),
                    'idr': f'{idr.valor} {idr.unidade}' if idr else 'IDR não cadastrado para este grupo',
                    'passo_4_pct_vd': (
                        f'({nutriente_ativo} {c.unidade_medida} / {idr.valor} {idr.unidade}) × 100 = {pct_vd}%'
                        if idr else 'N/A — sem IDR'
                    ),
                    'passo_5_arredondamento': regra_arredondamento,
                    'valor_final': float(valor_arredondado),
                    'lista_regulatoria': self.lista.versao,
                    'lista_id': self.lista.id,
                },
            }

        self._resultado = resultado
        return resultado

    # ------------------------------------------------------------------
    # IDR lookup (pode vir de outra lista regulatória — ver lista_idr)
    # ------------------------------------------------------------------

    def _buscar_idr(self, constituinte: Constituinte):
        """
        Localiza a IDR do constituinte para o grupo populacional atual.

        A IN 28/2018 define apenas limites mínimo/máximo; os valores de IDR
        usados no %VD vêm da RDC 269/2005. Quando a lista vigente aponta uma
        ``lista_idr``, a busca é feita lá — casando o constituinte pelo nome,
        já que cada lista tem seus próprios registros de Constituinte.
        """
        # 1) IDR na própria lista vigente
        idr = IDR.objects.filter(
            constituinte=constituinte,
            grupo_populacional=self.grupo,
            lista_regulatoria=self.lista,
        ).first()
        if idr:
            return idr

        # 2) IDR na lista de IDR vinculada, casando pelo nome do constituinte
        lista_idr = self.lista.lista_idr
        if not lista_idr:
            return None

        return IDR.objects.filter(
            constituinte__nome__iexact=constituinte.nome,
            constituinte__lista_regulatoria=lista_idr,
            grupo_populacional=self.grupo,
            lista_regulatoria=lista_idr,
        ).first()

    # ------------------------------------------------------------------
    # Unit conversion (g → declared unit)
    # ------------------------------------------------------------------

    def _converter_unidade(self, unidade: str) -> tuple[Decimal, str]:
        """
        Retorna (fator_multiplicador, descricao) para converter gramas
        para a unidade declarada do constituinte.

        A quantidade de matéria-prima é sempre em gramas (FormulacaoItem.quantidade_g).
        O fator_conversao da MP fornece a fração em g/g do nutriente puro.
        Este método converte o resultado (em g) para mg, mcg, etc.

        Exemplos:
          mg  → fator 1000  (1 g = 1000 mg)
          mcg → fator 1e6   (1 g = 1.000.000 mcg)
          g   → fator 1     (sem conversão)
          UFC → fator 1e9   (convenção: 1 g de probiótico = 10^9 UFC típico —
                              validar com laudo; o fator_conversao da MP já deve
                              refletir a contagem real em UFC/g)
        """
        u = unidade.lower().strip()
        if u == 'mg':
            return Decimal('1000'), 'g → mg (×1000)'
        if u in ('mcg', 'µg', 'μg'):
            return Decimal('1000000'), 'g → mcg (×1.000.000)'
        if u == 'g':
            return Decimal('1'), 'g → g (sem conversão)'
        if u in ('ui', 'iu'):
            # UI/IU: fator de conversão MP deve já estar em UI/g
            # neste caso fator_conversao já carrega UI por g de MP,
            # e o campo deve ser interpretado diretamente.
            return Decimal('1'), 'UI/IU: fator_conversao da MP já em UI/g'
        if u == 'ufc':
            # UFC: fator_conversao da MP em UFC/g (ex: 5×10^9 UFC/g = 5000000000)
            return Decimal('1'), 'UFC: fator_conversao da MP já em UFC/g'
        # Fallback: sem conversão — registrar para revisão
        return Decimal('1'), f'{unidade}: unidade não mapeada, sem conversão (revisar)'

    # ------------------------------------------------------------------
    # Rounding rules (ANVISA)
    # ------------------------------------------------------------------

    def _arredondar(self, valor: Decimal, constituinte: Constituinte) -> tuple[Decimal, str]:
        """
        Aplica as regras de arredondamento conforme ANVISA.

        Regras gerais para vitaminas/minerais:
        - mcg/µg: ≥5 → inteiro; <5 → 1 casa decimal
        - mg: ≥10 → inteiro; <10 → 1 casa decimal
        - Probióticos: arredondar para 10^8 UFC mais próximo
        - Demais: 2 casas decimais
        """
        unidade = constituinte.unidade_medida.lower().strip()
        tipo = constituinte.tipo

        if tipo == 'probiotico':
            # Arredondar para múltiplo de 10^8
            fator = Decimal('1E+8')
            arredondado = (valor / fator).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * fator
            return arredondado, f'Probiótico: arredondado para múltiplo de 10⁸ UFC → {arredondado} UFC'

        if unidade in ('mcg', 'µg', 'μg'):
            if valor >= 5:
                arredondado = valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                return arredondado, f'mcg ≥ 5: arredondado para inteiro → {arredondado} mcg'
            else:
                arredondado = valor.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                return arredondado, f'mcg < 5: 1 casa decimal → {arredondado} mcg'

        if unidade == 'mg':
            if valor >= 10:
                arredondado = valor.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                return arredondado, f'mg ≥ 10: arredondado para inteiro → {arredondado} mg'
            else:
                arredondado = valor.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                return arredondado, f'mg < 10: 1 casa decimal → {arredondado} mg'

        if unidade == 'g':
            if valor >= 1:
                arredondado = valor.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
                return arredondado, f'g ≥ 1: 1 casa decimal → {arredondado} g'
            else:
                arredondado = valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return arredondado, f'g < 1: 2 casas decimais → {arredondado} g'

        # Default: 2 decimal places
        arredondado = valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return arredondado, f'Padrão: 2 casas decimais → {arredondado} {constituinte.unidade_medida}'

    # ------------------------------------------------------------------
    # Compliance validation
    # ------------------------------------------------------------------

    def validar_conformidade(self) -> list[dict]:
        """
        Verifica se os valores calculados estão dentro dos limites
        mínimo e máximo definidos na lista regulatória vigente.

        Retorna lista de dicts com status: 'ok', 'abaixo_minimo', 'acima_maximo', 'sem_limite'.
        """
        if self._resultado is None:
            self.calcular_por_dose()

        violacoes = []

        for nome_c, dados in self._resultado.items():
            try:
                limite = LimiteConstituinte.objects.get(
                    constituinte_id=dados['constituinte_id'],
                    grupo_populacional=self.grupo,
                    lista_regulatoria=self.lista,
                )
                valor = Decimal(str(dados['valor_declarado']))

                if limite.limite_minimo and valor < limite.limite_minimo:
                    violacoes.append({
                        'constituinte': nome_c,
                        'status': 'abaixo_minimo',
                        'status_display': 'Abaixo do mínimo',
                        'valor': float(valor),
                        'unidade': dados['unidade'],
                        'limite_minimo': float(limite.limite_minimo),
                        'limite_maximo': float(limite.limite_maximo) if limite.limite_maximo else None,
                        'mensagem': (
                            f'{nome_c}: {valor} {dados["unidade"]} < mínimo permitido '
                            f'{limite.limite_minimo} {limite.unidade}'
                        ),
                    })
                elif limite.limite_maximo and valor > limite.limite_maximo:
                    violacoes.append({
                        'constituinte': nome_c,
                        'status': 'acima_maximo',
                        'status_display': 'Acima do máximo',
                        'valor': float(valor),
                        'unidade': dados['unidade'],
                        'limite_minimo': float(limite.limite_minimo) if limite.limite_minimo else None,
                        'limite_maximo': float(limite.limite_maximo),
                        'mensagem': (
                            f'{nome_c}: {valor} {dados["unidade"]} > máximo permitido '
                            f'{limite.limite_maximo} {limite.unidade}'
                        ),
                    })
                else:
                    violacoes.append({
                        'constituinte': nome_c,
                        'status': 'ok',
                        'status_display': 'Conforme',
                        'valor': float(valor),
                        'unidade': dados['unidade'],
                        'limite_minimo': float(limite.limite_minimo) if limite.limite_minimo else None,
                        'limite_maximo': float(limite.limite_maximo) if limite.limite_maximo else None,
                        'mensagem': (
                            f'{nome_c}: {valor} {dados["unidade"]} — dentro dos limites permitidos'
                        ),
                    })

            except LimiteConstituinte.DoesNotExist:
                violacoes.append({
                    'constituinte': nome_c,
                    'status': 'sem_limite',
                    'status_display': 'Sem limite cadastrado',
                    'valor': float(dados['valor_declarado']),
                    'unidade': dados['unidade'],
                    'limite_minimo': None,
                    'limite_maximo': None,
                    'mensagem': (
                        f'{nome_c}: sem limite cadastrado para '
                        f'"{self.grupo.nome}" nesta lista regulatória'
                    ),
                })

        return violacoes

    # ------------------------------------------------------------------
    # Mandatory warnings
    # ------------------------------------------------------------------

    def gerar_advertencias(self) -> list[dict]:
        """
        Retorna as advertências obrigatórias aplicáveis ao produto,
        baseado nos constituintes presentes e na lista regulatória vigente.
        """
        if self._resultado is None:
            self.calcular_por_dose()

        constituinte_ids = [d['constituinte_id'] for d in self._resultado.values()]

        advertencias_qs = AdvertenciaObrigatoria.objects.filter(
            lista_regulatoria=self.lista
        ).filter(
            dj_models.Q(constituinte_id__in=constituinte_ids)
            | dj_models.Q(constituinte__isnull=True)
        ).select_related('constituinte')

        return [
            {
                'texto': a.texto_advertencia,
                'condicao': a.condicao_texto,
                'constituinte': a.constituinte.nome if a.constituinte else 'Geral',
            }
            for a in advertencias_qs
        ]
