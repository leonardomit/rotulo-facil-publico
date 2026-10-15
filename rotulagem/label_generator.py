"""
Gerador de Rótulo — Rótulo Fácil Suplementos
=============================================
Consolida os resultados de MotorCalculo para múltiplos grupos populacionais
e monta todos os elementos obrigatórios do rótulo conforme RDC 243/2018,
IN 28/2018 e normativas aplicáveis.

IMPORTANTE: Suplementos alimentares são ISENTOS de rotulagem nutricional
frontal (lupa "ALTO EM"). Este gerador NUNCA produz esse elemento.
Referência: RDC 727/2022 Art. 43.
"""

from typing import Optional
from .models import (
    Produto, GrupoPopulacional, ListaRegulatoria,
    AlegacaoAutorizada, ALERGENOS_DICT,
)
from .engine import MotorCalculo


class GeradorRotulo:
    """
    Gera todos os elementos de rótulo para um produto, considerando
    múltiplos grupos populacionais.

    Uso::

        from rotulagem.label_generator import GeradorRotulo
        from rotulagem.models import Produto, GrupoPopulacional

        produto = Produto.objects.get(pk=1)
        grupos = list(produto.grupos_populacionais.all())
        gerador = GeradorRotulo(produto, grupos)
        rotulo = gerador.gerar()
    """

    def __init__(
        self,
        produto: Produto,
        grupos_populacionais: list,
        lista_regulatoria: Optional[ListaRegulatoria] = None,
    ):
        self.produto = produto
        self.grupos = grupos_populacionais
        try:
            self.lista = lista_regulatoria or ListaRegulatoria.objects.get(vigente=True)
        except ListaRegulatoria.DoesNotExist:
            raise ValueError(
                'Nenhuma Lista Regulatória vigente. '
                'Configure uma no painel administrativo.'
            )
        self._motores = {g: MotorCalculo(produto, g, self.lista) for g in grupos_populacionais}

    def gerar(self) -> dict:
        """
        Retorna dicionário completo com todos os elementos de rótulo.
        """
        resultados = {
            g.nome: motor.calcular_por_dose()
            for g, motor in self._motores.items()
        }

        return {
            'produto': {
                'nome': self.produto.nome,
                'marca': self.produto.marca,
                'forma_apresentacao': self.produto.get_forma_apresentacao_display(),
                'unidades_por_dose': float(self.produto.unidades_por_dose),
                'doses_por_embalagem': self.produto.doses_por_embalagem,
                'medida_caseira': self.produto.medida_caseira,
            },
            'denominacao_legal': self._denominacao_legal(),
            'lista_ingredientes': self._lista_ingredientes(),
            'alergenos': self._alergenos(),
            'tabela_nutricional': resultados,
            'recomendacao_uso': self._recomendacao_uso(),
            'advertencias': self._advertencias(),
            'alegacoes': self._alegacoes_autorizadas(),
            'aviso_transgenico': self._aviso_transgenico(),
            'lista_regulatoria': {
                'versao': self.lista.versao,
                'fonte': self.lista.fonte,
                'data_vigencia': str(self.lista.data_vigencia),
            },
            # AVISO CRÍTICO — manter sempre visível no output
            'nota_lupa': (
                'PROIBIDO PARA SUPLEMENTOS: Rotulagem nutricional frontal (lupa "ALTO EM") '
                'NÃO se aplica a suplementos alimentares. '
                'Referência: RDC 727/2022 Art. 43 — suplementos são isentos.'
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _denominacao_legal(self) -> str:
        """
        Monta a denominação legal do produto conforme RDC 243/2018.
        Formato: "Suplemento Alimentar de [tipos] — [forma de apresentação]"
        """
        if self.produto.denominacao_legal:
            return self.produto.denominacao_legal
        tipos = set()
        for item in self.produto.formulacao.select_related('materia_prima__constituinte'):
            if item.materia_prima.constituinte:
                tipos.add(item.materia_prima.constituinte.get_tipo_display())
        tipo_str = ', '.join(sorted(tipos))
        return (
            f'Suplemento Alimentar de {tipo_str} '
            f'— {self.produto.get_forma_apresentacao_display()}'
        )

    def _lista_ingredientes(self) -> list[str]:
        """
        Lista de ingredientes em ordem decrescente de quantidade (RDC 243/2018 Art. 18).
        Aditivos alimentares seguem o formato: nome [função INS nº].
        """
        itens = self.produto.formulacao.select_related('materia_prima').order_by('-quantidade_g')
        resultado = []
        for item in itens:
            mp = item.materia_prima
            ingrediente = mp.nome_comercial
            if mp.aditivo and mp.funcao_aditivo:
                ins = f' INS {mp.ins_aditivo}' if mp.ins_aditivo else ''
                ingrediente += f' [{mp.funcao_aditivo}{ins}]'
            resultado.append(ingrediente)
        return resultado

    def _alergenos(self) -> dict:
        """
        Coleta todos os alérgenos presentes nas matérias-primas (RDC 26/2015).
        Retorna dicionário com 'contem' (lista de nomes) e 'pode_conter' (cross-contaminação).
        """
        codigos_contem = set()
        for item in self.produto.formulacao.select_related('materia_prima'):
            for codigo in item.materia_prima.alergenos:
                codigos_contem.add(codigo)

        contem = [ALERGENOS_DICT.get(c, c) for c in sorted(codigos_contem)]

        return {
            'contem': contem,
            'pode_conter': [],  # Preenchido manualmente pelo usuário (contaminação cruzada)
        }

    def _recomendacao_uso(self) -> str:
        """
        Monta o texto de recomendação de consumo (RDC 243/2018 Art. 19).
        """
        grupos = ', '.join([g.nome for g in self.produto.grupos_populacionais.all()])
        dose = f'{self.produto.unidades_por_dose} {self.produto.get_forma_apresentacao_display()}'
        if float(self.produto.unidades_por_dose) != 1:
            dose += '(s)'
        if self.produto.medida_caseira:
            dose += f' ({self.produto.medida_caseira})'
        return f'Consumir {dose} ao dia. Indicado para: {grupos}.'

    def _alegacoes_autorizadas(self) -> list[str]:
        """
        Retorna alegações funcionais/saúde autorizadas para os constituintes
        presentes na formulação (IN 28/2018 e normativas associadas).
        """
        constituinte_ids = [
            item.materia_prima.constituinte_id
            for item in self.produto.formulacao.select_related('materia_prima')
            if item.materia_prima.constituinte_id
        ]
        return list(
            AlegacaoAutorizada.objects.filter(
                constituinte_id__in=constituinte_ids,
                lista_regulatoria=self.lista,
            ).values_list('texto_alegacao', flat=True)
        )

    def _advertencias(self) -> list[dict]:
        """
        Coleta advertências obrigatórias de todos os grupos populacionais,
        deduplicando por texto.
        """
        advertencias = []
        for g, motor in self._motores.items():
            advertencias.extend(motor.gerar_advertencias())

        # Deduplicar por texto da advertência
        seen = set()
        dedup = []
        for a in advertencias:
            if a['texto'] not in seen:
                seen.add(a['texto'])
                dedup.append(a)
        return dedup

    def _aviso_transgenico(self) -> Optional[str]:
        """
        Gera o aviso de transgênico se alguma matéria-prima for transgênica
        (Lei 11.105/2005 e Decreto 4.680/2003).
        """
        for item in self.produto.formulacao.select_related('materia_prima'):
            if item.materia_prima.transgenico:
                return (
                    '(Transgênico) Contém ingrediente(s) produzido(s) a partir de '
                    'organismos geneticamente modificados.'
                )
        return None


class GeradorRotuloAlimento:
    """
    Gera os elementos de rótulo para produtos da categoria ALIMENTO,
    conforme RDC 429/2020, IN 75/2020, RDC 727/2022 (rotulagem geral)
    e RDC 26/2015 (alérgenos).

    Diferenças em relação a suplementos:
    - Tabela nutricional com dupla declaração (por 100 g/ml e por porção) e %VD;
    - Rotulagem nutricional frontal (lupa "ALTO EM") quando limites forem atingidos;
    - Sem IDR, limites de constituintes, alegações ou advertências da IN 28/2018.
    """

    def __init__(self, produto: Produto, lista_regulatoria: Optional[ListaRegulatoria] = None):
        from .engine_alimentos import MotorCalculoAlimento
        self.produto = produto
        self.motor = MotorCalculoAlimento(produto, lista_regulatoria)

    def gerar(self) -> dict:
        calculo = self.motor.calcular()
        porcao = calculo['porcao']
        porcao_txt = f'{porcao["valor"]:g} {porcao["unidade"]}'
        if porcao['medida_caseira']:
            porcao_txt += f' ({porcao["medida_caseira"]})'

        return {
            'categoria': 'alimento',
            'produto': {
                'nome': self.produto.nome,
                'marca': self.produto.marca,
                'forma_apresentacao': self.produto.get_forma_apresentacao_display(),
                'porcao': porcao_txt,
                'porcoes_por_embalagem': porcao['porcoes_por_embalagem'],
            },
            'denominacao_legal': self._denominacao_legal(),
            'lista_ingredientes': self._lista_ingredientes(),
            'alergenos': self._alergenos(),
            'tabela_nutricional': calculo,
            'lupa': calculo['lupa'],
            'avisos': calculo['avisos'],
            'aviso_transgenico': self._aviso_transgenico(),
            'lista_regulatoria': {
                'versao': self.motor.lista.versao,
                'fonte': self.motor.lista.fonte,
                'data_vigencia': str(self.motor.lista.data_vigencia),
            },
        }

    def _denominacao_legal(self) -> str:
        if self.produto.denominacao_legal:
            return self.produto.denominacao_legal
        return f'{self.produto.nome} — {self.produto.get_forma_apresentacao_display()}'

    # Ingredientes, alérgenos e transgênico seguem as mesmas regras dos
    # suplementos (RDC 727/2022, RDC 26/2015, Decreto 4.680/2003)
    _lista_ingredientes = GeradorRotulo._lista_ingredientes
    _alergenos = GeradorRotulo._alergenos
    _aviso_transgenico = GeradorRotulo._aviso_transgenico

