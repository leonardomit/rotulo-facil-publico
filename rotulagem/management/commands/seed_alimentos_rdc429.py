"""
Seed regulatório de ALIMENTOS — RDC 429/2020 + IN 75/2020
==========================================================
Cria a lista regulatória de alimentos com:
- Valores Diários de referência (VD) para %VD — IN 75/2020 (dieta de 2.000 kcal);
- Limites da rotulagem nutricional frontal (lupa "ALTO EM") — RDC 429/2020.

A lista NÃO é marcada como vigente: o flag `vigente` continua reservado à
lista de suplementos (IN 28/2018). O motor de alimentos localiza esta lista
pela presença dos Valores Diários.
"""

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand

from rotulagem.models import ListaRegulatoria, ValorDiarioReferencia, LimiteLupa

# IN 75/2020 — Valores Diários de referência (dieta de 2.000 kcal)
VALORES_DIARIOS = [
    ('energia', Decimal('2000'), 'kcal'),
    ('carboidratos', Decimal('300'), 'g'),
    ('acucares_adicionados', Decimal('50'), 'g'),
    ('proteinas', Decimal('50'), 'g'),
    ('gorduras_totais', Decimal('65'), 'g'),
    ('gorduras_saturadas', Decimal('20'), 'g'),
    ('fibras', Decimal('25'), 'g'),
    ('sodio', Decimal('2000'), 'mg'),
    # Açúcares totais e gorduras trans NÃO possuem VD (não declarar %VD)
]

# RDC 429/2020 — limites da rotulagem nutricional frontal (lupa)
LIMITES_LUPA = [
    ('acucares_adicionados', 'solido', Decimal('15'), 'g', 'ALTO EM AÇÚCAR ADICIONADO'),
    ('acucares_adicionados', 'liquido', Decimal('7.5'), 'g', 'ALTO EM AÇÚCAR ADICIONADO'),
    ('gorduras_saturadas', 'solido', Decimal('6'), 'g', 'ALTO EM GORDURA SATURADA'),
    ('gorduras_saturadas', 'liquido', Decimal('3'), 'g', 'ALTO EM GORDURA SATURADA'),
    ('sodio', 'solido', Decimal('600'), 'mg', 'ALTO EM SÓDIO'),
    ('sodio', 'liquido', Decimal('300'), 'mg', 'ALTO EM SÓDIO'),
]


class Command(BaseCommand):
    help = 'Popula a lista regulatória de alimentos (RDC 429/2020 + IN 75/2020)'

    def handle(self, *args, **options):
        lista, criada = ListaRegulatoria.objects.get_or_create(
            versao='RDC429-2020-v1',
            defaults={
                'nome': 'Rotulagem Nutricional de Alimentos',
                'fonte': 'RDC 429/2020 + IN 75/2020',
                'vigente': False,
                'data_vigencia': date(2022, 10, 9),
                'observacoes': (
                    'Lista para ALIMENTOS: Valores Diários de referência (IN 75/2020) '
                    'e limites da rotulagem nutricional frontal (RDC 429/2020). '
                    'Não usa o flag "vigente" — este permanece na lista de suplementos.'
                ),
            },
        )
        self.stdout.write(
            f'Lista {"criada" if criada else "já existente"}: {lista.nome} [{lista.versao}]'
        )

        for nutriente, valor, unidade in VALORES_DIARIOS:
            _, criado = ValorDiarioReferencia.objects.update_or_create(
                nutriente=nutriente,
                lista_regulatoria=lista,
                defaults={'valor': valor, 'unidade': unidade},
            )
            self.stdout.write(
                f'  VD {"+" if criado else "="} {nutriente}: {valor} {unidade}'
            )

        for nutriente, base, valor, unidade, rotulo in LIMITES_LUPA:
            _, criado = LimiteLupa.objects.update_or_create(
                nutriente=nutriente,
                base=base,
                lista_regulatoria=lista,
                defaults={'valor': valor, 'unidade': unidade, 'rotulo_frontal': rotulo},
            )
            self.stdout.write(
                f'  Lupa {"+" if criado else "="} {rotulo} ({base}): ≥ {valor} {unidade}/100'
            )

        self.stdout.write(self.style.SUCCESS('Seed de alimentos concluído.'))
