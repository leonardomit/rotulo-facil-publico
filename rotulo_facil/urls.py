from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.templatetags.static import static as static_url
from django.views.generic.base import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    # O browser pede /favicon.ico na raiz mesmo com o <link> no template
    # (e o admin do Django não estende o base.html).
    path('favicon.ico', RedirectView.as_view(url=static_url('favicon.ico'))),
    path('', include('rotulagem.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = 'Rótulo Fácil Suplementos — Admin'
admin.site.site_title = 'Rótulo Fácil'
admin.site.index_title = 'Painel Administrativo'
