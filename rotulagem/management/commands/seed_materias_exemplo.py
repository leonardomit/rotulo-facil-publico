"""
Management command: seed_materias_exemplo
==========================================
Cria matérias-primas de exemplo vinculadas aos constituintes da lista
regulatória **vigente** (normalmente a IN 28/2018 importada do dash de OPs).

Diferente do ``seed_regulatorio``, este comando NÃO cria nem altera listas
regulatórias — ele apenas cadastra matérias-primas apontando para os
constituintes que já existem, preservando a vigência configurada.

Quando encontra uma FonteAutorizada correspondente na IN 28, registra a forma
química oficial na matéria-prima.

Uso:
    python manage.py seed_materias_exemplo
    python manage.py seed_materias_exemplo --substituir   # recria as de exemplo
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from rotulagem.models import (
    Constituinte, FonteAutorizada, ListaRegulatoria, MateriaPrima,
)

# ---------------------------------------------------------------------------
# Matérias-primas de exemplo
#
# fator_conversao = % de nutriente ativo por grama de matéria-prima
# fonte_in28      = nome (ou trecho) da forma química na lista da IN 28/2018
# ---------------------------------------------------------------------------
MATERIAS = [
    {
        'nome_comercial': 'Ácido Ascórbico 100%',
        'nome_cientifico': 'Ascorbic Acid USP',
        'constituinte': 'Vitamina C',
        'fator_conversao': Decimal('100'),
        'fornecedor': 'DSM / BASF',
        'fonte_in28': 'Ácido ascórbico',
        'observacoes': 'Ativo puro — 1 g fornece 1000 mg de vitamina C.',
    },
    {
        'nome_comercial': 'Colecalciferol 1% (100.000 UI/g)',
        'nome_cientifico': 'Cholecalciferol 1% CWS',
        'constituinte': 'Vitamina D',
        'fator_conversao': Decimal('1'),
        'fornecedor': 'DSM',
        'fonte_in28': 'Colecalciferol',
        'observacoes': 'Microencapsulado em celulose. 1 g fornece 10 mg (10.000 mcg) de vitamina D.',
    },
    {
        'nome_comercial': 'Bisglicinato de Ferro 20%',
        'nome_cientifico': 'Ferrous Bisglycinate Chelate',
        'constituinte': 'Ferro',
        'fator_conversao': Decimal('20'),
        'fornecedor': 'Albion / Balchem',
        'fonte_in28': 'Bisglicinato de ferro',
        'observacoes': 'Quelato de alta biodisponibilidade — 20% de ferro elementar.',
    },
    {
        'nome_comercial': 'Carbonato de Cálcio 40%',
        'nome_cientifico': 'Calcium Carbonate food grade',
        'constituinte': 'Cálcio',
        'fator_conversao': Decimal('40'),
        'fornecedor': 'Omya / Imerys',
        'fonte_in28': 'Carbonato de cálcio',
        'observacoes': '40% de cálcio elementar por grama.',
    },
    {
        'nome_comercial': 'Óxido de Zinco 80%',
        'nome_cientifico': 'Zinc Oxide food grade',
        'constituinte': 'Zinco',
        'fator_conversao': Decimal('80'),
        'fornecedor': 'EverZinc',
        'fonte_in28': 'Óxido de zinco',
        'observacoes': '80% de zinco elementar por grama.',
    },
    {
        'nome_comercial': 'Bisglicinato de Magnésio 14%',
        'nome_cientifico': 'Magnesium Bisglycinate Chelate',
        'constituinte': 'Magnésio',
        'fator_conversao': Decimal('14'),
        'fornecedor': 'Albion / Balchem',
        'fonte_in28': 'Bisglicinato de magnésio',
        'observacoes': 'Quelato de boa tolerância gastrointestinal.',
    },
    {
        'nome_comercial': 'Metilcobalamina 1%',
        'nome_cientifico': 'Methylcobalamin 1%',
        'constituinte': 'Vitamina B12',
        'fator_conversao': Decimal('1'),
        'fornecedor': 'DSM',
        'fonte_in28': 'Metilcobalamina',
        'observacoes': 'Forma ativa da B12. 1 g fornece 10 mg (10.000 mcg).',
    },
]


class Command(BaseCommand):
    help = 'Cria matérias-primas de exemplo ligadas aos constituintes da lista vigente'

    def add_arguments(self, parser):
        parser.add_argument('--substituir', action='store_true',
                            help='Apaga e recria as matérias-primas de exemplo')

    @transaction.atomic
    def handle(self, *args, **opts):
        self.stdout.write(self.style.HTTP_INFO(
            '▶ Criando matérias-primas de exemplo…\n'))

        lista = ListaRegulatoria.objects.filter(vigente=True).first()
        if not lista:
            self.stderr.write(self.style.ERROR(
                'Nenhuma lista regulatória vigente. Rode antes:\n'
                '  python manage.py importar_in28'))
            return

        self.stdout.write(f'  Lista vigente: {lista.versao}\n')

        admin = User.objects.filter(username='admin').first()

        if opts['substituir']:
            nomes = [m['nome_comercial'] for m in MATERIAS]
            n = MateriaPrima.objects.filter(nome_comercial__in=nomes).delete()[0]
            if n:
                self.stdout.write(self.style.WARNING(f'  {n} registro(s) removido(s)\n'))

        criadas = puladas = faltando = 0

        for m in MATERIAS:
            const = Constituinte.objects.filter(
                nome__iexact=m['constituinte'], lista_regulatoria=lista
            ).first()

            if not const:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ {m["nome_comercial"]}: constituinte '
                    f'"{m["constituinte"]}" não existe na lista vigente — pulado'))
                faltando += 1
                continue

            # Forma química oficial, quando existir na lista da IN 28
            fonte = FonteAutorizada.objects.filter(
                constituinte=const, nome__icontains=m['fonte_in28']
            ).first()
            forma = fonte.nome if fonte else m['fonte_in28']

            mp, novo = MateriaPrima.objects.get_or_create(
                nome_comercial=m['nome_comercial'],
                defaults={
                    'nome_cientifico': m['nome_cientifico'],
                    'constituinte': const,
                    'fator_conversao': m['fator_conversao'],
                    'unidade_medida': 'g',
                    'fornecedor': m['fornecedor'],
                    'forma_quimica': forma,
                    'alergenos': [],
                    'transgenico': False,
                    'aditivo': False,
                    'ativo': True,
                    'observacoes': m['observacoes'],
                    'created_by': admin,
                },
            )

            if novo:
                criadas += 1
                selo = '✓ (forma oficial IN 28)' if fonte else '✓'
                self.stdout.write(
                    f'  {selo} {mp.nome_comercial} — '
                    f'{mp.fator_conversao}% de {const.nome} [{const.unidade_medida}]')
            else:
                puladas += 1
                self.stdout.write(f'  → já existe: {mp.nome_comercial}')

        self.stdout.write('\n' + '=' * 62)
        self.stdout.write(self.style.SUCCESS('✅ Matérias-primas de exemplo prontas\n'))
        self.stdout.write(f'   Criadas          : {criadas}')
        self.stdout.write(f'   Já existiam      : {puladas}')
        if faltando:
            self.stdout.write(self.style.WARNING(
                f'   Puladas (s/ const): {faltando}'))
        self.stdout.write(f'   Total no sistema : {MateriaPrima.objects.count()}')
        self.stdout.write('=' * 62)
