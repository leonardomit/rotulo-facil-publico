"""
Management command: seed_regulatorio
=====================================
Popula o banco de dados com a lista regulatória IN 28/2018 e dados de exemplo
para permitir o funcionamento imediato do sistema.

Todos os valores são baseados em:
- IN 28/2018 (IDR adultos e limites)
- RDC 243/2018 (grupos populacionais)

Execute: python manage.py seed_regulatorio
"""
import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from rotulagem.models import (
    GrupoPopulacional, ListaRegulatoria, Constituinte, IDR,
    LimiteConstituinte, AdvertenciaObrigatoria, MateriaPrima,
)


class Command(BaseCommand):
    help = 'Seed banco de dados com lista regulatória IN 28/2018 e dados de exemplo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear', action='store_true',
            help='Apaga todos os dados regulatórios antes de inserir (use com cuidado!)'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Apagando dados regulatórios existentes…'))
            MateriaPrima.objects.all().delete()
            IDR.objects.all().delete()
            LimiteConstituinte.objects.all().delete()
            AdvertenciaObrigatoria.objects.all().delete()
            Constituinte.objects.all().delete()
            ListaRegulatoria.objects.all().delete()
            GrupoPopulacional.objects.all().delete()

        self.stdout.write(self.style.HTTP_INFO('▶ Iniciando seed_regulatorio…\n'))

        # ----------------------------------------------------------------
        # 1. Grupos Populacionais (RDC 243/2018, Art. 6)
        # ----------------------------------------------------------------
        self.stdout.write('1. Criando Grupos Populacionais…')
        grupos_def = [
            {'nome': 'Adultos (19-59 anos)',      'faixa_min': 19,  'faixa_max': 59,  'descricao': 'Adultos de 19 a 59 anos'},
            {'nome': 'Gestantes',                 'faixa_min': None,'faixa_max': None, 'descricao': 'Mulheres grávidas'},
            {'nome': 'Lactantes',                 'faixa_min': None,'faixa_max': None, 'descricao': 'Mulheres em fase de amamentação'},
            {'nome': 'Crianças 4-8 anos',         'faixa_min': 4,   'faixa_max': 8,   'descricao': 'Crianças de 4 a 8 anos'},
            {'nome': 'Crianças 9-13 anos',        'faixa_min': 9,   'faixa_max': 13,  'descricao': 'Crianças de 9 a 13 anos'},
            {'nome': 'Adolescentes 14-18 anos',   'faixa_min': 14,  'faixa_max': 18,  'descricao': 'Adolescentes de 14 a 18 anos'},
            {'nome': 'Idosos 60+ anos',           'faixa_min': 60,  'faixa_max': None, 'descricao': 'Idosos acima de 60 anos'},
        ]
        grupos = {}
        for gd in grupos_def:
            g, created = GrupoPopulacional.objects.get_or_create(
                nome=gd['nome'],
                defaults={
                    'descricao': gd['descricao'],
                    'faixa_etaria_min': gd['faixa_min'],
                    'faixa_etaria_max': gd['faixa_max'],
                }
            )
            grupos[gd['nome']] = g
            status = '✓ criado' if created else '→ já existe'
            self.stdout.write(f'   {status}: {g.nome}')

        adultos = grupos['Adultos (19-59 anos)']

        # ----------------------------------------------------------------
        # 2. Lista Regulatória — IN 28/2018
        # ----------------------------------------------------------------
        self.stdout.write('\n2. Criando Lista Regulatória IN 28/2018…')
        lista, created = ListaRegulatoria.objects.get_or_create(
            versao='IN28-2018-v1',
            defaults={
                'nome': 'IN 28/2018 — IDR e Limites de Vitaminas e Minerais',
                'fonte': 'IN 28/2018 Anexo III — Tabela de IDR e Limites',
                'vigente': True,
                'data_vigencia': datetime.date(2018, 6, 26),
                'observacoes': (
                    'Instrução Normativa nº 28 de 26/06/2018. '
                    'Define IDR e limites mínimos/máximos de vitaminas e minerais '
                    'para suplementos alimentares. Inclui atualizações de IN 275/2024.'
                ),
            }
        )
        status = '✓ criada' if created else '→ já existe'
        self.stdout.write(f'   {status}: {lista}')

        # ----------------------------------------------------------------
        # 3. Constituintes + IDR Adultos + Limites
        #    Fonte: IN 28/2018 Anexo III
        # ----------------------------------------------------------------
        self.stdout.write('\n3. Criando Constituintes, IDR e Limites (grupo Adultos)…')

        nutrientes = [
            # (nome, tipo, unidade, idr, lim_min, lim_max, nome_cientifico)
            ('Vitamina C',    'vitamina', 'mg',  45.0,  7.5,    2000.0,  'Ácido Ascórbico'),
            ('Vitamina D',    'vitamina', 'mcg',  5.0,  0.84,    100.0,  'Colecalciferol / Ergocalciferol'),
            ('Vitamina E',    'vitamina', 'mg',  10.0,  1.68,    300.0,  'alfa-Tocoferol'),
            ('Vitamina B12',  'vitamina', 'mcg',  2.4,  0.4,     600.0,  'Cianocobalamina / Metilcobalamina'),
            ('Ácido Fólico',  'vitamina', 'mcg', 240.0, 40.0,   1000.0,  'Ácido Pteroilglutâmico'),
            ('Vitamina A',    'vitamina', 'mcg', 600.0, 100.0,  3000.0,  'Retinol / beta-Caroteno'),
            ('Vitamina B6',   'vitamina', 'mg',   1.3,  0.22,    100.0,  'Piridoxina'),
            ('Niacina (B3)',  'vitamina', 'mg',  16.0,  2.67,     35.0,  'Ácido Nicotínico / Nicotinamida'),
            ('Vitamina K',    'vitamina', 'mcg', 90.0,  15.0,   1000.0,  'Filoquinona / Menaquinona'),
            ('Ferro',         'mineral',  'mg',  14.0,  2.34,     45.0,  'Ferro elementar'),
            ('Cálcio',        'mineral',  'mg', 1000.0, 167.0,  2500.0,  '—'),
            ('Zinco',         'mineral',  'mg',   7.0,  1.17,     40.0,  '—'),
            ('Magnésio',      'mineral',  'mg', 260.0,  43.4,    400.0,  '—'),
            ('Iodo',          'mineral',  'mcg', 150.0, 25.0,    600.0,  '—'),
            ('Selênio',       'mineral',  'mcg', 34.0,  5.67,    300.0,  '—'),
        ]

        constituintes = {}
        for nome, tipo, unidade, idr_val, lim_min, lim_max, nome_cient in nutrientes:
            # Constituinte
            c, c_created = Constituinte.objects.get_or_create(
                nome=nome,
                lista_regulatoria=lista,
                defaults={
                    'nome_cientifico': nome_cient if nome_cient != '—' else '',
                    'tipo': tipo,
                    'unidade_medida': unidade,
                    'autorizado': True,
                    'anexo_referencia': 'IN 28/2018 Anexo III',
                }
            )
            constituintes[nome] = c

            # IDR para Adultos
            idr_obj, _ = IDR.objects.get_or_create(
                constituinte=c,
                grupo_populacional=adultos,
                lista_regulatoria=lista,
                defaults={'valor': idr_val, 'unidade': unidade},
            )

            # Limites para Adultos
            LimiteConstituinte.objects.get_or_create(
                constituinte=c,
                grupo_populacional=adultos,
                lista_regulatoria=lista,
                defaults={
                    'limite_minimo': lim_min,
                    'limite_maximo': lim_max,
                    'unidade': unidade,
                    'observacoes': 'Fonte: IN 28/2018 Anexo III',
                }
            )

            status = '✓' if c_created else '→'
            self.stdout.write(
                f'   {status} {nome}: IDR={idr_val}{unidade}, '
                f'lim=[{lim_min}–{lim_max}]{unidade}'
            )

        # ----------------------------------------------------------------
        # 4. Advertência obrigatória geral
        # ----------------------------------------------------------------
        self.stdout.write('\n4. Criando Advertência Obrigatória Geral…')
        adv, created = AdvertenciaObrigatoria.objects.get_or_create(
            condicao_texto='Advertência obrigatória para todos os suplementos alimentares',
            lista_regulatoria=lista,
            defaults={
                'constituinte': None,
                'texto_advertencia': (
                    'Este produto não é um medicamento e não substitui '
                    'uma alimentação equilibrada e um estilo de vida saudável.'
                ),
            }
        )
        status = '✓ criada' if created else '→ já existe'
        self.stdout.write(f'   {status}: Advertência geral')

        # ----------------------------------------------------------------
        # 5. Matérias-primas de exemplo
        # ----------------------------------------------------------------
        self.stdout.write('\n5. Criando Matérias-Primas de exemplo…')

        # Try to get admin user for created_by
        try:
            admin_user = User.objects.get(username='admin')
        except User.DoesNotExist:
            admin_user = None

        mps_def = [
            {
                'nome_comercial': 'Ácido Ascórbico 100%',
                'nome_cientifico': 'Ascorbic Acid USP',
                'constituinte_nome': 'Vitamina C',
                'fator_conversao': 100.0,
                'fornecedor': 'BASF / DSM',
                'forma_quimica': 'Ácido L-Ascórbico cristalino',
                'observacoes': 'Fator de conversão = 100% pois é o ativo puro.',
            },
            {
                'nome_comercial': 'Colecalciferol 1% em celulose',
                'nome_cientifico': 'Cholecalciferol 1%',
                'constituinte_nome': 'Vitamina D',
                'fator_conversao': 1.0,
                'fornecedor': 'DSM',
                'forma_quimica': 'Colecalciferol microencapsulado 1% em celulose microcristalina',
                'observacoes': '1% = 10.000 UI/g. Fator: 1g de MP = 0,01g de Vit. D pura.',
            },
            {
                'nome_comercial': 'Bisglicinato de Ferro 20%',
                'nome_cientifico': 'Ferrous Bisglycinate Chelate 20%',
                'constituinte_nome': 'Ferro',
                'fator_conversao': 20.0,
                'fornecedor': 'Albion / Balchem',
                'forma_quimica': 'Bisglicinato de ferro quelado TRAACS®',
                'observacoes': '20% de ferro elementar por grama de quelato.',
            },
            {
                'nome_comercial': 'Carbonato de Cálcio 40%',
                'nome_cientifico': 'Calcium Carbonate food grade',
                'constituinte_nome': 'Cálcio',
                'fator_conversao': 40.0,
                'fornecedor': 'Omya / Imerys',
                'forma_quimica': 'Carbonato de cálcio precipitado grau alimentício',
                'observacoes': '40% de cálcio elementar por grama de carbonato de cálcio.',
            },
            {
                'nome_comercial': 'Óxido de Zinco 80%',
                'nome_cientifico': 'Zinc Oxide food grade',
                'constituinte_nome': 'Zinco',
                'fator_conversao': 80.0,
                'fornecedor': 'EverZinc',
                'forma_quimica': 'Óxido de zinco grau alimentício',
                'observacoes': '80% de zinco elementar por grama de óxido de zinco.',
            },
        ]

        for mpd in mps_def:
            c = constituintes.get(mpd['constituinte_nome'])
            if not c:
                self.stdout.write(self.style.WARNING(
                    f'   ⚠ Constituinte "{mpd["constituinte_nome"]}" não encontrado, pulando MP.'
                ))
                continue

            mp, created = MateriaPrima.objects.get_or_create(
                nome_comercial=mpd['nome_comercial'],
                defaults={
                    'nome_cientifico': mpd['nome_cientifico'],
                    'constituinte': c,
                    'fator_conversao': mpd['fator_conversao'],
                    'unidade_medida': 'g',
                    'fornecedor': mpd['fornecedor'],
                    'forma_quimica': mpd['forma_quimica'],
                    'alergenos': [],
                    'transgenico': False,
                    'aditivo': False,
                    'ativo': True,
                    'observacoes': mpd['observacoes'],
                    'created_by': admin_user,
                }
            )
            status = '✓ criada' if created else '→ já existe'
            self.stdout.write(
                f'   {status}: {mp.nome_comercial} '
                f'({mp.fator_conversao}% {mp.constituinte.nome})'
            )

        # ----------------------------------------------------------------
        # Summary
        # ----------------------------------------------------------------
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('✅ seed_regulatorio concluído com sucesso!\n'))
        self.stdout.write(f'   Grupos Populacionais : {GrupoPopulacional.objects.count()}')
        self.stdout.write(f'   Listas Regulatórias  : {ListaRegulatoria.objects.count()} (vigente: {lista.versao})')
        self.stdout.write(f'   Constituintes        : {Constituinte.objects.count()}')
        self.stdout.write(f'   IDRs cadastrados     : {IDR.objects.count()}')
        self.stdout.write(f'   Limites cadastrados  : {LimiteConstituinte.objects.count()}')
        self.stdout.write(f'   Matérias-Primas      : {MateriaPrima.objects.count()}')
        self.stdout.write(f'   Advertências         : {AdvertenciaObrigatoria.objects.count()}')
        self.stdout.write('='*60)
        self.stdout.write(
            self.style.NOTICE(
                '\n💡 Para criar o superusuário admin:\n'
                '   python manage.py createsuperuser --username admin --email admin@example.com\n'
                '\n💡 Para iniciar o servidor:\n'
                '   python manage.py runserver\n'
            )
        )
