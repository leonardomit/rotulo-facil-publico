import io

from django.contrib import admin, messages
from django.core.management import call_command
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html

from .importador_in28 import CAMINHOS_PADRAO, localizar_banco
from .models import (
    GrupoPopulacional, ListaRegulatoria, Constituinte, IDR,
    LimiteConstituinte, AlegacaoAutorizada, AdvertenciaObrigatoria,
    FonteAutorizada, MateriaPrima, Produto, FormulacaoItem, VersaoProduto,
    CalculoLog, ComposicaoNutricional, ValorDiarioReferencia, LimiteLupa,
)


# ---------------------------------------------------------------------------
# Regulatory admin
# ---------------------------------------------------------------------------

@admin.register(GrupoPopulacional)
class GrupoPopulacionalAdmin(admin.ModelAdmin):
    list_display = ['nome', 'faixa_etaria_min', 'faixa_etaria_max', 'descricao']
    search_fields = ['nome']


@admin.register(ListaRegulatoria)
class ListaRegulatoriaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'versao', 'fonte', 'vigente_badge', 'idr_badge',
                    'data_vigencia', 'created_at']
    list_filter = ['vigente']
    search_fields = ['nome', 'versao', 'fonte']
    readonly_fields = ['created_at', 'created_by']
    change_list_template = 'admin/rotulagem/listaregulatoria/change_list.html'

    def vigente_badge(self, obj):
        if obj.vigente:
            return format_html('<b style="color:#00996E">✓ Vigente</b>')
        return format_html('<span style="color:#8B8377">Inativa</span>')
    vigente_badge.short_description = 'Status'

    def idr_badge(self, obj):
        if obj.idrs.exists():
            return format_html('<span style="color:#00996E">IDR própria</span>')
        if obj.lista_idr:
            return format_html('<span style="color:#5C564C">IDR ← {}</span>',
                               obj.lista_idr.versao)
        return format_html('<b style="color:#C0402E">sem IDR</b>')
    idr_badge.short_description = 'Origem da IDR'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    # ------------------------------------------------------------------
    # Importação da IN 28 e das IDRs — botões na listagem
    # ------------------------------------------------------------------

    def get_urls(self):
        extras = [
            path('importar-in28/', self.admin_site.admin_view(self.view_importar_in28),
                 name='rotulagem_listaregulatoria_importar_in28'),
            path('importar-idr/', self.admin_site.admin_view(self.view_importar_idr),
                 name='rotulagem_listaregulatoria_importar_idr'),
        ]
        return extras + super().get_urls()

    def _url_listagem(self):
        return reverse('admin:rotulagem_listaregulatoria_changelist')

    def view_importar_in28(self, request):
        """Tela de confirmação + execução da importação da IN 28/2018."""
        try:
            caminho = localizar_banco(request.POST.get('banco') or None)
            erro_banco = None
        except FileNotFoundError as e:
            caminho, erro_banco = None, str(e)

        if request.method == 'POST' and not erro_banco:
            dry = bool(request.POST.get('dry_run'))
            buf = io.StringIO()
            try:
                call_command('importar_in28', banco=str(caminho),
                             dry_run=dry, stdout=buf, stderr=buf)
            except Exception as e:
                self.message_user(request, f'Falha na importação: {e}',
                                  level=messages.ERROR)
                return HttpResponseRedirect(self._url_listagem())

            saida = buf.getvalue()
            return render(request, 'admin/rotulagem/importacao_resultado.html', {
                **self.admin_site.each_context(request),
                'title': 'Simulação da importação' if dry else 'Importação concluída',
                'saida': saida,
                'dry_run': dry,
                'url_voltar': self._url_listagem(),
            })

        return render(request, 'admin/rotulagem/importar_in28.html', {
            **self.admin_site.each_context(request),
            'title': 'Importar lista IN 28/2018',
            'caminho': caminho,
            'erro_banco': erro_banco,
            'caminhos_padrao': CAMINHOS_PADRAO,
            'url_voltar': self._url_listagem(),
        })

    def view_importar_idr(self, request):
        """Executa o seed das IDRs da RDC 269/2005."""
        if request.method != 'POST':
            return HttpResponseRedirect(self._url_listagem())

        buf = io.StringIO()
        try:
            call_command('seed_idr_rdc269', stdout=buf, stderr=buf)
        except Exception as e:
            self.message_user(request, f'Falha ao popular IDRs: {e}',
                              level=messages.ERROR)
            return HttpResponseRedirect(self._url_listagem())

        return render(request, 'admin/rotulagem/importacao_resultado.html', {
            **self.admin_site.each_context(request),
            'title': 'IDRs da RDC 269/2005 populadas',
            'saida': buf.getvalue(),
            'dry_run': False,
            'url_voltar': self._url_listagem(),
        })


class IDRInline(admin.TabularInline):
    model = IDR
    extra = 0
    fields = ['grupo_populacional', 'valor', 'unidade', 'lista_regulatoria']
    autocomplete_fields = ['grupo_populacional']


class LimiteInline(admin.TabularInline):
    model = LimiteConstituinte
    extra = 0
    fields = ['grupo_populacional', 'limite_minimo', 'limite_maximo', 'unidade', 'lista_regulatoria']


class AlegacaoInline(admin.TabularInline):
    model = AlegacaoAutorizada
    extra = 0
    fields = ['texto_alegacao', 'condicoes', 'lista_regulatoria']


class FonteAutorizadaInline(admin.TabularInline):
    model = FonteAutorizada
    extra = 0
    fields = ['nome', 'cas', 'categoria', 'funcao']
    show_change_link = True


@admin.register(Constituinte)
class ConstituinteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'tipo', 'unidade_medida', 'autorizado',
                    'qtd_fontes', 'lista_regulatoria', 'anexo_referencia']
    list_filter = ['tipo', 'autorizado', 'lista_regulatoria']
    search_fields = ['nome', 'nome_cientifico']
    inlines = [FonteAutorizadaInline, IDRInline, LimiteInline, AlegacaoInline]

    def qtd_fontes(self, obj):
        return obj.fontes_autorizadas.count()
    qtd_fontes.short_description = 'Fontes'


@admin.register(FonteAutorizada)
class FonteAutorizadaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'constituinte', 'categoria', 'cas', 'lista_regulatoria']
    list_filter = ['categoria', 'lista_regulatoria', 'constituinte__tipo']
    search_fields = ['nome', 'cas', 'constituinte__nome', 'funcao']
    autocomplete_fields = ['constituinte']


@admin.register(IDR)
class IDRAdmin(admin.ModelAdmin):
    list_display = ['constituinte', 'grupo_populacional', 'valor', 'unidade', 'lista_regulatoria']
    list_filter = ['grupo_populacional', 'lista_regulatoria', 'constituinte__tipo']
    search_fields = ['constituinte__nome', 'grupo_populacional__nome']
    autocomplete_fields = ['constituinte', 'grupo_populacional']


@admin.register(LimiteConstituinte)
class LimiteConstituinteAdmin(admin.ModelAdmin):
    list_display = ['constituinte', 'grupo_populacional', 'limite_minimo', 'limite_maximo',
                    'unidade', 'lista_regulatoria']
    list_filter = ['grupo_populacional', 'lista_regulatoria']
    search_fields = ['constituinte__nome']
    autocomplete_fields = ['constituinte', 'grupo_populacional']


@admin.register(AlegacaoAutorizada)
class AlegacaoAutorizadaAdmin(admin.ModelAdmin):
    list_display = ['constituinte', 'texto_alegacao_curto', 'lista_regulatoria']
    list_filter = ['lista_regulatoria']
    search_fields = ['constituinte__nome', 'texto_alegacao']

    def texto_alegacao_curto(self, obj):
        return obj.texto_alegacao[:80] + ('…' if len(obj.texto_alegacao) > 80 else '')
    texto_alegacao_curto.short_description = 'Alegação'


@admin.register(AdvertenciaObrigatoria)
class AdvertenciaObrigatoriaAdmin(admin.ModelAdmin):
    list_display = ['constituinte_ou_geral', 'texto_curto', 'lista_regulatoria']
    list_filter = ['lista_regulatoria']

    def constituinte_ou_geral(self, obj):
        return obj.constituinte.nome if obj.constituinte else '⚠ GERAL'
    constituinte_ou_geral.short_description = 'Constituinte / Escopo'

    def texto_curto(self, obj):
        return obj.texto_advertencia[:80] + ('…' if len(obj.texto_advertencia) > 80 else '')
    texto_curto.short_description = 'Advertência'


# ---------------------------------------------------------------------------
# Raw materials admin
# ---------------------------------------------------------------------------

class ComposicaoNutricionalInline(admin.StackedInline):
    model = ComposicaoNutricional
    extra = 0


@admin.register(MateriaPrima)
class MateriaPrimaAdmin(admin.ModelAdmin):
    list_display = ['nome_comercial', 'constituinte', 'fator_conversao', 'fornecedor',
                    'aditivo', 'transgenico', 'tem_composicao', 'ativo']
    list_filter = ['ativo', 'aditivo', 'transgenico', 'constituinte__tipo']
    search_fields = ['nome_comercial', 'nome_cientifico', 'constituinte__nome']
    readonly_fields = ['created_at', 'updated_at', 'created_by']
    inlines = [ComposicaoNutricionalInline]

    def tem_composicao(self, obj):
        return hasattr(obj, 'composicao')
    tem_composicao.boolean = True
    tem_composicao.short_description = 'Composição (alimentos)'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ---------------------------------------------------------------------------
# Products admin
# ---------------------------------------------------------------------------

class FormulacaoItemInline(admin.TabularInline):
    model = FormulacaoItem
    extra = 1
    fields = ['ordem', 'materia_prima', 'quantidade_g', 'overage_pct']
    autocomplete_fields = ['materia_prima']


@admin.register(ValorDiarioReferencia)
class ValorDiarioReferenciaAdmin(admin.ModelAdmin):
    list_display = ['nutriente', 'valor', 'unidade', 'lista_regulatoria']
    list_filter = ['lista_regulatoria']


@admin.register(LimiteLupa)
class LimiteLupaAdmin(admin.ModelAdmin):
    list_display = ['rotulo_frontal', 'nutriente', 'base', 'valor', 'unidade',
                    'lista_regulatoria']
    list_filter = ['base', 'lista_regulatoria']


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ['nome', 'marca', 'categoria', 'forma_apresentacao', 'versao_atual',
                    'ativo', 'updated_at']
    list_filter = ['ativo', 'categoria', 'forma_apresentacao', 'grupos_populacionais']
    search_fields = ['nome', 'marca']
    filter_horizontal = ['grupos_populacionais']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'versao_atual']
    inlines = [FormulacaoItemInline]

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(VersaoProduto)
class VersaoProdutoAdmin(admin.ModelAdmin):
    list_display = ['produto', 'versao_numero', 'created_by', 'created_at']
    list_filter = ['produto']
    readonly_fields = ['produto', 'versao_numero', 'snapshot_json', 'created_by', 'created_at']

    def has_add_permission(self, request):
        return False


@admin.register(CalculoLog)
class CalculoLogAdmin(admin.ModelAdmin):
    list_display = ['produto', 'usuario', 'data_calculo', 'lista_regulatoria_usada']
    list_filter = ['lista_regulatoria_usada', 'produto']
    readonly_fields = ['produto', 'usuario', 'data_calculo', 'lista_regulatoria_usada',
                       'resultado_json', 'grupos_calculados']

    def has_add_permission(self, request):
        return False
