"""
Management command: seed_idr_rdc269
====================================
Popula a tabela IDR com os valores da **RDC nº 269, de 22/09/2005** — o
"Regulamento Técnico sobre a Ingestão Diária Recomendada (IDR) de Proteína,
Vitaminas e Minerais".

Por que esta norma?
-------------------
A IN 28/2018 define apenas os LIMITES mínimos e máximos de cada constituinte
em suplementos. O percentual de Valor Diário (%VD) declarado no rótulo, porém,
deve ser calculado sobre a IDR da RDC 269/2005 — que continua vigente e é a
referência oficial para suplementos alimentares.

Fonte: RDC 269/2005, Anexo — Tabela de IDR por grupo populacional.
       https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2005/rdc0269_22_09_2005.html

Uso:
    python manage.py seed_idr_rdc269
    python manage.py seed_idr_rdc269 --versao=RDC269-2005
"""

import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from rotulagem.models import (
    Constituinte, GrupoPopulacional, IDR, ListaRegulatoria,
)

# ---------------------------------------------------------------------------
# Grupos populacionais da RDC 269/2005
# ---------------------------------------------------------------------------
GRUPOS_RDC269 = [
    ('Lactentes 0 a 6 meses',              0,    0,    'Lactentes de 0 a 6 meses'),
    ('Lactentes 7 a 11 meses',             0,    0,    'Lactentes de 7 a 11 meses'),
    ('Crianças 1 a 3 anos',                1,    3,    'Crianças de 1 a 3 anos'),
    ('Crianças 4 a 8 anos',                4,    8,    'Crianças de 4 a 8 anos'),
    ('Crianças e adolescentes 9 a 18 anos', 9,   18,   'Crianças e adolescentes de 9 a 18 anos'),
    ('Adultos maiores de 19 anos',         19,   None, 'Adultos com 19 anos ou mais'),
    ('Gestantes',                          None, None, 'Mulheres grávidas'),
    ('Lactantes',                          None, None, 'Mulheres em fase de amamentação'),
]

# ---------------------------------------------------------------------------
# Tabela de IDR — RDC 269/2005
#
# Ordem dos valores (8 grupos, alinhada a GRUPOS_RDC269):
#   0-6m | 7-11m | 1-3a | 4-8a | 9-18a | 19+ | Gestantes | Lactantes
#
# ``None`` = IDR não estabelecida para o grupo naquela norma.
# ---------------------------------------------------------------------------
TABELA_IDR = [
    # (nome, tipo, unidade, [8 valores])
    ('Proteína',           'proteina', 'g',   [9.1,  13.5, 13,   19,   47,   50,   71,   71]),

    # -- Vitaminas ---------------------------------------------------------
    ('Vitamina A',         'vitamina', 'mcg', [375,  400,  400,  450,  600,  600,  800,  850]),
    ('Vitamina D',         'vitamina', 'mcg', [5,    5,    5,    5,    5,    5,    5,    5]),
    ('Vitamina E',         'vitamina', 'mg',  [2.7,  2.7,  5,    6,    11,   10,   10,   12]),
    ('Vitamina K',         'vitamina', 'mcg', [5,    10,   15,   25,   55,   65,   55,   55]),
    ('Vitamina C',         'vitamina', 'mg',  [25,   30,   30,   30,   45,   45,   55,   70]),
    ('Tiamina (B1)',       'vitamina', 'mg',  [0.2,  0.3,  0.5,  0.6,  1.1,  1.2,  1.4,  1.5]),
    ('Riboflavina (B2)',   'vitamina', 'mg',  [0.3,  0.4,  0.5,  0.6,  1.0,  1.3,  1.4,  1.6]),
    ('Niacina (B3)',       'vitamina', 'mg',  [2,    4,    6,    8,    16,   16,   18,   17]),
    ('Vitamina B6',        'vitamina', 'mg',  [0.1,  0.3,  0.5,  0.6,  1.3,  1.3,  1.9,  2.0]),
    ('Ácido Fólico',       'vitamina', 'mcg', [80,   80,   150,  200,  300,  240,  600,  500]),
    ('Vitamina B12',       'vitamina', 'mcg', [0.4,  0.7,  0.9,  1.2,  2.4,  2.4,  2.6,  2.8]),
    ('Ácido Pantotênico',  'vitamina', 'mg',  [1.7,  1.8,  2,    3,    5,    5,    6,    7]),
    ('Biotina',            'vitamina', 'mcg', [5,    6,    8,    12,   25,   30,   30,   35]),

    # -- Minerais ----------------------------------------------------------
    ('Cálcio',             'mineral',  'mg',  [300,  400,  500,  600,  1300, 1000, 1200, 1000]),
    ('Ferro',              'mineral',  'mg',  [0.27, 6.9,  5.8,  5.9,  11.7, 14,   27,   15]),
    ('Magnésio',           'mineral',  'mg',  [30,   75,   80,   130,  260,  260,  220,  270]),
    ('Zinco',              'mineral',  'mg',  [2.8,  4.1,  4.1,  5.6,  9.8,  7,    11,   12]),
    ('Iodo',               'mineral',  'mcg', [110,  130,  90,   90,   130,  150,  200,  200]),
    ('Fósforo',            'mineral',  'mg',  [100,  275,  460,  500,  1250, 700,  700,  700]),
    ('Selênio',            'mineral',  'mcg', [15,   20,   17,   21,   32,   34,   30,   35]),
    ('Cobre',              'mineral',  'mcg', [200,  220,  340,  440,  700,  900,  1000, 1300]),
    ('Manganês',           'mineral',  'mg',  [0.003, 0.6, 1.2,  1.5,  2.2,  2.3,  2,    2.6]),
    ('Flúor',              'mineral',  'mg',  [0.01, 0.5,  0.7,  1,    2,    4,    3,    3]),
    ('Molibdênio',         'mineral',  'mcg', [2,    3,    17,   22,   34,   45,   50,   50]),
    ('Cromo',              'mineral',  'mcg', [0.2,  5.5,  11,   15,   25,   35,   30,   45]),
]


class Command(BaseCommand):
    help = 'Popula os valores de IDR conforme a RDC 269/2005 (base do %VD)'

    def add_arguments(self, parser):
        parser.add_argument('--versao', default='RDC269-2005',
                            help='Versão da ListaRegulatoria de IDR')
        parser.add_argument('--dry-run', action='store_true',
                            help='Simula sem gravar')

    @transaction.atomic
    def handle(self, *args, **opts):
        dry = opts['dry_run']
        sid = transaction.savepoint()

        self.stdout.write(self.style.HTTP_INFO(
            '▶ Populando IDRs da RDC 269/2005…\n'))
        if dry:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN — nada será gravado\n'))

        # ------------------------------------------------------------------
        # Lista regulatória de IDR (separada da lista de limites da IN 28)
        # ------------------------------------------------------------------
        lista, criada = ListaRegulatoria.objects.get_or_create(
            versao=opts['versao'],
            defaults={
                'nome': 'RDC 269/2005 — IDR de Proteína, Vitaminas e Minerais',
                'fonte': 'RDC nº 269, de 22/09/2005 — Anexo (Tabela de IDR)',
                'vigente': False,   # a lista vigente é a de limites (IN 28)
                'data_vigencia': datetime.date(2005, 9, 23),
                'observacoes': (
                    'Valores de Ingestão Diária Recomendada usados como base do '
                    'cálculo de %VD nos rótulos de suplementos alimentares. '
                    'A IN 28/2018 define apenas limites mínimos/máximos — a IDR '
                    'para o %VD vem desta norma.\n'
                    'https://bvsms.saude.gov.br/bvs/saudelegis/anvisa/2005/'
                    'rdc0269_22_09_2005.html'
                ),
            }
        )
        self.stdout.write(
            f'  Lista: {lista.versao} ({"criada" if criada else "já existia"})\n')

        # ------------------------------------------------------------------
        # Grupos populacionais
        # ------------------------------------------------------------------
        grupos = []
        for nome, fmin, fmax, desc in GRUPOS_RDC269:
            g, _ = GrupoPopulacional.objects.get_or_create(
                nome=nome,
                defaults={'descricao': desc,
                          'faixa_etaria_min': fmin, 'faixa_etaria_max': fmax},
            )
            grupos.append(g)
        self.stdout.write(f'  {len(grupos)} grupos populacionais prontos\n')

        # ------------------------------------------------------------------
        # Constituintes + IDRs
        # ------------------------------------------------------------------
        n_const = n_idr = 0
        self.stdout.write('  Constituintes e IDRs:')

        for nome, tipo, unidade, valores in TABELA_IDR:
            const, novo = Constituinte.objects.get_or_create(
                nome=nome,
                lista_regulatoria=lista,
                defaults={
                    'tipo': tipo,
                    'unidade_medida': unidade,
                    'autorizado': True,
                    'anexo_referencia': 'RDC 269/2005 — Anexo (IDR)',
                },
            )
            if novo:
                n_const += 1

            criados_grupo = 0
            for grupo, valor in zip(grupos, valores):
                if valor is None:
                    continue
                _, novo_idr = IDR.objects.get_or_create(
                    constituinte=const,
                    grupo_populacional=grupo,
                    lista_regulatoria=lista,
                    defaults={'valor': valor, 'unidade': unidade},
                )
                if novo_idr:
                    criados_grupo += 1
            n_idr += criados_grupo

            adulto = valores[5]
            self.stdout.write(
                f'    {"✓" if novo else "→"} {nome:22s} '
                f'adulto={adulto}{unidade:4s} ({criados_grupo} grupos)')

        # ------------------------------------------------------------------
        # Vincula esta lista de IDR às listas de limites que ainda não têm uma
        # ------------------------------------------------------------------
        vinculadas = ListaRegulatoria.objects.filter(
            lista_idr__isnull=True
        ).exclude(pk=lista.pk).update(lista_idr=lista)
        if vinculadas:
            self.stdout.write(
                f'\n  {vinculadas} lista(s) de limites agora usam esta IDR para o %VD')

        if dry:
            transaction.savepoint_rollback(sid)
        else:
            transaction.savepoint_commit(sid)

        # ------------------------------------------------------------------
        self.stdout.write('\n' + '=' * 62)
        titulo = 'SIMULAÇÃO concluída (nada gravado)' if dry else 'IDRs populadas!'
        self.stdout.write(self.style.SUCCESS(f'✅ {titulo}\n'))
        self.stdout.write(f'   Constituintes criados : {n_const}')
        self.stdout.write(f'   IDRs criadas          : {n_idr}')
        self.stdout.write(f'   Grupos populacionais  : {len(grupos)}')
        self.stdout.write('=' * 62)
        self.stdout.write(self.style.NOTICE(
            '\n⚠  A IDR e os limites vivem em listas regulatórias separadas:\n'
            '   • RDC269-2005      → IDR (base do %VD)\n'
            '   • IN28-2018-ANVISA → limites mínimo/máximo\n'
            '   O MotorCalculo usa a lista marcada como vigente; ajuste no Admin\n'
            '   conforme a necessidade de cada cálculo.\n'))
