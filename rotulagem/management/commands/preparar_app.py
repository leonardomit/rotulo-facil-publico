"""
Management command: preparar_app
=================================
Prepara o Rótulo Fácil para o primeiro uso (idempotente — pode rodar sempre):

1. Aplica as migrações do banco;
2. Carrega os dados regulatórios da fixture ``dados_regulatorios.json``
   (apenas se o banco ainda não os tiver);
3. Garante o usuário administrador inicial (admin, senha aleatória mostrada
   uma única vez, na criação).

Usado pelos atalhos ``iniciar.command`` (macOS) e ``INICIAR-WINDOWS.bat``.
"""

import secrets

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Prepara o app para o primeiro uso: migrações, dados regulatórios e admin'

    def handle(self, *args, **options):
        self.stdout.write('→ Aplicando migrações...')
        call_command('migrate', interactive=False, verbosity=0)
        self.stdout.write(self.style.SUCCESS('  Banco atualizado.'))

        from rotulagem.models import Constituinte
        total = Constituinte.objects.count()
        if total:
            self.stdout.write(f'→ Dados regulatórios já carregados ({total} constituintes).')
        else:
            self.stdout.write('→ Carregando dados regulatórios (IN 28/2018, RDC 269/2005, RDC 429/2020)...')
            call_command('loaddata', 'dados_regulatorios.json', verbosity=0)
            self.stdout.write(self.style.SUCCESS(
                f'  {Constituinte.objects.count()} constituintes carregados.'
            ))

        user, novo = User.objects.get_or_create(
            username='admin', defaults={'email': 'admin@example.com'}
        )
        user.is_staff = user.is_superuser = True
        if novo:
            senha = secrets.token_urlsafe(9)
            user.set_password(senha)
            self.stdout.write(self.style.WARNING(
                f'→ Usuário "admin" criado. Senha inicial: {senha}\n'
                '  Anote agora — ela não será mostrada de novo. Troque no primeiro acesso.'
            ))
        else:
            self.stdout.write('→ Usuário "admin" já existe.')
        user.save()

        self.stdout.write(self.style.SUCCESS('Tudo pronto.'))
