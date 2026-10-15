from django.conf import settings


def apps_externos(request):
    """Expõe no template os atalhos para os apps irmãos.

    Vem de variável de ambiente (`REGULA_URL`) porque esta é a distribuição
    entregue a terceiros: sem a variável configurada o botão não aparece, e
    nenhuma cópia do app sai apontando para o Regula da Fitobrasil.
    """
    return {'REGULA_URL': settings.REGULA_URL}
