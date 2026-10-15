import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rotulo_facil.settings')
application = get_wsgi_application()

# O builder Python da Vercel procura a variável ``app``.
app = application


def _log(msg):
    print(f'[boot] {msg}', file=sys.stderr, flush=True)


def _migrar_se_preciso():
    """Aplica migrações pendentes no boot — nada a fazer no caso comum.

    Em serverless não há passo de release, e depender de uma env var para
    migrar já custou caro: o django-axes entrou no projeto sem que suas
    tabelas fossem criadas no Postgres, e todo login passou a devolver 500.
    Consultar o plano de migrações é barato (uma query em django_migrations),
    então a checagem roda sempre e o migrate só quando há o que aplicar.
    """
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connections['default'])
    plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if not plano:
        return
    pendentes = ', '.join(f'{m.app_label}.{m.name}' for m, _ in plano)
    _log(f'migrações pendentes: {pendentes}')
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    _log('migrações aplicadas.')


# Um banco fora do ar não pode impedir o app de subir: sem isso a instância
# morre no import e nem a tela de login é servida.
try:
    _migrar_se_preciso()
except Exception as e:
    _log(f'migrate falhou: {e!r}')

# Com PREPARAR_APP_NO_BOOT=1 roda o preparar_app inteiro (migrações, seed
# regulatório e admin inicial) — necessário só no primeiro deploy de um banco
# vazio; depois disso a checagem de migrações acima basta.
if os.environ.get('PREPARAR_APP_NO_BOOT') == '1':
    _log('preparar_app iniciando...')
    try:
        from django.core.management import call_command
        call_command('preparar_app')
        _log('preparar_app concluido.')
    except Exception as e:
        _log(f'preparar_app falhou: {e!r}')
