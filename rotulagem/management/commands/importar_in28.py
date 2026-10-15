"""
Management command: importar_in28
==================================
Importa a lista oficial de constituintes da IN 28/2018 a partir do banco do
dashboard de OPs (lotes_manuais.db, tabela ``powerbi_constituintes``).

Popula: Constituinte, FonteAutorizada, LimiteConstituinte,
        AlegacaoAutorizada, AdvertenciaObrigatoria.

Uso:
    python manage.py importar_in28
    python manage.py importar_in28 --banco=/caminho/lotes_manuais.db
    python manage.py importar_in28 --dry-run
    python manage.py importar_in28 --versao=IN28-2018-v2

NOTA: esta tabela contém LIMITES (mínimo/máximo), não IDR.
Para os valores de IDR use: python manage.py seed_idr_rdc269
"""

import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from rotulagem.importador_in28 import (
    GRUPOS_ANVISA, MAPA_TIPO, localizar_banco, ler_powerbi_constituintes,
    normalizar_nutriente, parse_limite, tem_alegacao,
)
from rotulagem.models import (
    AdvertenciaObrigatoria, AlegacaoAutorizada, Constituinte, FonteAutorizada,
    GrupoPopulacional, LimiteConstituinte, ListaRegulatoria,
)


class Command(BaseCommand):
    help = 'Importa constituintes, limites, alegações e advertências da IN 28/2018'

    def add_arguments(self, parser):
        parser.add_argument('--banco', default=None,
                            help='Caminho para lotes_manuais.db')
        parser.add_argument('--versao', default='IN28-2018-ANVISA',
                            help='Versão da ListaRegulatoria a criar/atualizar')
        parser.add_argument('--dry-run', action='store_true',
                            help='Simula a importação sem gravar nada')
        parser.add_argument('--nao-vigente', action='store_true',
                            help='Importa sem marcar a lista como vigente')

    def handle(self, *args, **opts):
        dry = opts['dry_run']

        self.stdout.write(self.style.HTTP_INFO(
            '▶ Importando lista de constituintes da IN 28/2018…\n'))

        # ------------------------------------------------------------------
        # 1. Ler banco de origem
        # ------------------------------------------------------------------
        try:
            caminho = localizar_banco(opts['banco'])
        except FileNotFoundError as e:
            self.stderr.write(self.style.ERROR(str(e)))
            return

        self.stdout.write(f'  Origem: {caminho}')
        colunas, linhas, total, atualizado_em = ler_powerbi_constituintes(caminho)
        self.stdout.write(
            f'  {len(linhas)} registros (total declarado: {total}) '
            f'— atualizado em {atualizado_em}\n')

        if dry:
            self.stdout.write(self.style.WARNING('  MODO DRY-RUN — nada será gravado\n'))

        resumo = self._importar(linhas, opts, dry, atualizado_em)
        self._relatorio(resumo, dry)

    # ----------------------------------------------------------------------

    @transaction.atomic
    def _importar(self, linhas, opts, dry, atualizado_em):
        sid = transaction.savepoint()

        # ------------------------------------------------------------------
        # Lista regulatória versionada
        # ------------------------------------------------------------------
        lista, criada = ListaRegulatoria.objects.get_or_create(
            versao=opts['versao'],
            defaults={
                'nome': 'IN 28/2018 — Constituintes, Limites, Alegações e Rotulagem',
                'fonte': 'IN 28/2018 Anexos I a VII (via dashboard de OPs / Power BI ANVISA)',
                'vigente': not opts['nao_vigente'],
                'data_vigencia': datetime.date(2018, 7, 26),
                'observacoes': (
                    'Importado automaticamente da tabela powerbi_constituintes '
                    f'do dashboard de OPs. Snapshot da fonte: {atualizado_em}. '
                    'Contém LIMITES mínimos/máximos por grupo populacional — '
                    'os valores de IDR para %VD vêm da RDC 269/2005.'
                ),
            }
        )
        self.stdout.write(
            f'  Lista regulatória: {lista.versao} '
            f'({"criada" if criada else "já existia"})')

        # Vincula automaticamente a lista de IDR (RDC 269/2005), se já existir.
        # A IN 28 não traz IDR — sem esse vínculo o %VD fica indisponível.
        if not lista.lista_idr:
            lista_idr = ListaRegulatoria.objects.filter(
                versao__startswith='RDC269'
            ).first()
            if lista_idr:
                lista.lista_idr = lista_idr
                lista.save(update_fields=['lista_idr'])
                self.stdout.write(f'  IDR vinculada a: {lista_idr.versao}')
            else:
                self.stdout.write(self.style.WARNING(
                    '  ⚠ Nenhuma lista de IDR encontrada — rode '
                    '"seed_idr_rdc269" para habilitar o cálculo de %VD'))
        self.stdout.write('')

        # ------------------------------------------------------------------
        # Grupos populacionais da IN 28
        # ------------------------------------------------------------------
        grupos = {}
        for idx, nome, fmin, fmax, desc in GRUPOS_ANVISA:
            g, _ = GrupoPopulacional.objects.get_or_create(
                nome=nome,
                defaults={'descricao': desc,
                          'faixa_etaria_min': fmin, 'faixa_etaria_max': fmax},
            )
            grupos[idx] = g
        self.stdout.write(f'  {len(grupos)} grupos populacionais prontos\n')

        # ------------------------------------------------------------------
        # Percorre os registros
        # ------------------------------------------------------------------
        c = {k: 0 for k in ('constituintes', 'fontes', 'limites', 'alegacoes',
                            'advertencias', 'multiplos', 'sem_nutriente',
                            'conflitos')}
        cache_const = {}
        vistos_aleg, vistos_adv = set(), set()
        conflitos_vistos = {}

        for l in linhas:
            def col(i):
                return (l[i] or '').strip() if i < len(l) else ''

            categoria = col(0)
            fonte_nome = col(1)
            nutriente = normalizar_nutriente(col(17)) or normalizar_nutriente(fonte_nome)

            if not nutriente:
                c['sem_nutriente'] += 1
                continue

            tipo = MAPA_TIPO.get(categoria.lower(), 'outro')

            # -- unidade predominante do constituinte (primeira célula válida)
            unidade = ''
            for idx, *_ in GRUPOS_ANVISA:
                p = parse_limite(col(idx))
                if p['autorizado'] and p['unidade']:
                    unidade = p['unidade']
                    break

            # -- Constituinte (deduplicado por nome)
            chave = nutriente.lower()
            if chave in cache_const:
                const = cache_const[chave]
                if not const.unidade_medida and unidade:
                    const.unidade_medida = unidade
                    const.save(update_fields=['unidade_medida'])
            else:
                const, novo = Constituinte.objects.get_or_create(
                    nome=nutriente,
                    lista_regulatoria=lista,
                    defaults={
                        'tipo': tipo,
                        'unidade_medida': unidade or 'mg',
                        'autorizado': True,
                        'anexo_referencia': f'IN 28/2018 — {categoria}',
                    },
                )
                cache_const[chave] = const
                if novo:
                    c['constituintes'] += 1

            # -- Fonte autorizada (forma química)
            if fonte_nome:
                _, novo = FonteAutorizada.objects.get_or_create(
                    nome=fonte_nome[:400],
                    constituinte=const,
                    lista_regulatoria=lista,
                    defaults={
                        'cas': col(2)[:100],
                        'categoria': categoria[:100],
                        'funcao': col(3),
                        'especificacoes': col(14),
                        'observacoes': col(15),
                        'outras_informacoes': col(16),
                        'link_especificacoes': col(18)[:500] if col(18).startswith('http') else '',
                    },
                )
                if novo:
                    c['fontes'] += 1

            # -- Limites por grupo populacional
            for idx, *_ in GRUPOS_ANVISA:
                p = parse_limite(col(idx))
                if not p['autorizado']:
                    continue
                if p['multiplo']:
                    c['multiplos'] += 1

                obs = 'Fonte: IN 28/2018'
                if p['multiplo']:
                    obs += (' — ATENÇÃO: célula com múltiplos nutrientes; '
                            'apenas o primeiro bloco foi parseado.')
                obs += f'\n\nTexto original ({fonte_nome}):\n{p["bruto"]}'

                limite, novo = LimiteConstituinte.objects.get_or_create(
                    constituinte=const,
                    grupo_populacional=grupos[idx],
                    lista_regulatoria=lista,
                    defaults={
                        'limite_minimo': p['minimo'],
                        'limite_maximo': p['maximo'],
                        'unidade': p['unidade'] or const.unidade_medida,
                        'observacoes': obs,
                    },
                )
                if novo:
                    c['limites'] += 1
                else:
                    # Fontes diferentes do mesmo nutriente podem trazer limites
                    # divergentes. Não sobrescreve: registra o conflito para
                    # revisão manual — usar o valor errado reprovaria/aprovaria
                    # um produto indevidamente.
                    def _difere(a, b):
                        if a is None or b is None:
                            return a is not b
                        return abs(Decimal(a) - Decimal(b)) > Decimal('0.0001')

                    if (_difere(limite.limite_minimo, p['minimo'])
                            or _difere(limite.limite_maximo, p['maximo'])):
                        c['conflitos'] += 1
                        chave_c = (const.nome, grupos[idx].nome)
                        if chave_c not in conflitos_vistos:
                            conflitos_vistos[chave_c] = []
                        conflitos_vistos[chave_c].append(
                            f'{fonte_nome}: {p["minimo"]}–{p["maximo"]} {p["unidade"]}')

                        marca = '\n\n⚠ CONFLITO — outra fonte declara limite diferente:\n'
                        if marca not in limite.observacoes:
                            limite.observacoes += marca
                        limite.observacoes += (
                            f'  • {fonte_nome}: {p["minimo"]}–{p["maximo"]} {p["unidade"]}\n')
                        limite.save(update_fields=['observacoes'])

            # -- Alegação autorizada
            texto_aleg = col(12)
            if tem_alegacao(texto_aleg):
                chave_a = (const.pk, texto_aleg[:200])
                if chave_a not in vistos_aleg:
                    vistos_aleg.add(chave_a)
                    _, novo = AlegacaoAutorizada.objects.get_or_create(
                        constituinte=const,
                        texto_alegacao=texto_aleg,
                        lista_regulatoria=lista,
                        defaults={'condicoes': col(13)},
                    )
                    if novo:
                        c['alegacoes'] += 1

            # -- Advertência / rotulagem complementar
            texto_adv = col(13)
            if texto_adv and len(texto_adv) > 3:
                chave_d = (const.pk, texto_adv[:200])
                if chave_d not in vistos_adv:
                    vistos_adv.add(chave_d)
                    _, novo = AdvertenciaObrigatoria.objects.get_or_create(
                        constituinte=const,
                        texto_advertencia=texto_adv,
                        lista_regulatoria=lista,
                        defaults={
                            'condicao_texto': (
                                f'Quando o produto contiver {const.nome} '
                                f'(IN 28/2018 — rotulagem complementar)'
                            ),
                        },
                    )
                    if novo:
                        c['advertencias'] += 1

        if dry:
            transaction.savepoint_rollback(sid)
        else:
            transaction.savepoint_commit(sid)

        c['lista'] = lista
        c['detalhe_conflitos'] = conflitos_vistos
        return c

    # ----------------------------------------------------------------------

    def _relatorio(self, c, dry):
        self.stdout.write('\n' + '=' * 62)
        titulo = 'SIMULAÇÃO concluída (nada gravado)' if dry else 'Importação concluída!'
        self.stdout.write(self.style.SUCCESS(f'✅ {titulo}\n'))
        self.stdout.write(f'   Constituintes criados : {c["constituintes"]}')
        self.stdout.write(f'   Fontes autorizadas    : {c["fontes"]}')
        self.stdout.write(f'   Limites criados       : {c["limites"]}')
        self.stdout.write(f'   Alegações criadas     : {c["alegacoes"]}')
        self.stdout.write(f'   Advertências criadas  : {c["advertencias"]}')
        if c['multiplos']:
            self.stdout.write(self.style.WARNING(
                f'   ⚠ Células multi-nutriente : {c["multiplos"]} '
                '(revisar manualmente — texto original em "observações")'))
        if c['sem_nutriente']:
            self.stdout.write(self.style.WARNING(
                f'   ⚠ Registros sem nutriente : {c["sem_nutriente"]} (ignorados)'))
        self.stdout.write('=' * 62)

        detalhe = c.get('detalhe_conflitos') or {}
        if detalhe:
            self.stdout.write(self.style.WARNING(
                f'\n⚠ LIMITES DIVERGENTES ENTRE FONTES — {len(detalhe)} '
                f'nutriente(s)/grupo(s), {c["conflitos"]} ocorrência(s).\n'
                '  Foi mantido o primeiro valor lido; os demais estão registrados\n'
                '  no campo "observações" de cada limite. REVISE antes de usar:\n'))
            for (nome, grupo), fontes in list(detalhe.items())[:12]:
                self.stdout.write(f'    • {nome} / {grupo}')
                for f in fontes[:3]:
                    self.stdout.write(f'        {f}')
            if len(detalhe) > 12:
                self.stdout.write(f'    … e mais {len(detalhe) - 12}')

        if not dry:
            self.stdout.write(self.style.NOTICE(
                '\n💡 Esta lista traz apenas LIMITES mínimos/máximos.\n'
                '   Para os valores de IDR (usados no cálculo de %VD), rode:\n'
                '   python manage.py seed_idr_rdc269\n'))
