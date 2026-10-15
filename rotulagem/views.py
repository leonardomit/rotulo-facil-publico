import json
import os
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View,
)
from django.views.generic.edit import FormView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Produto, MateriaPrima, Constituinte, GrupoPopulacional,
    ListaRegulatoria, FormulacaoItem, VersaoProduto, CalculoLog,
)
from .forms import (
    ProdutoForm, FormulacaoItemFormSet, MateriaPrimaForm, CalculoFiltroForm,
    ComposicaoNutricionalForm,
)
from .engine import MotorCalculo
from .engine_alimentos import MotorCalculoAlimento
from .label_generator import GeradorRotulo, GeradorRotuloAlimento


def _ops_token_ok(request):
    """Valida o header ``X-Seed-Token`` contra o OPS_TOKEN em tempo constante.
    Sem OPS_TOKEN configurado, os endpoints operacionais ficam desativados."""
    import secrets
    from django.conf import settings
    token = request.headers.get('X-Seed-Token', '')
    return bool(settings.OPS_TOKEN) and secrets.compare_digest(token, settings.OPS_TOKEN)


def healthz(request):
    """Liveness público mínimo; diagnóstico e seed só com o OPS_TOKEN.

    Com o token: ``?migrate=1`` aplica só as migrações pendentes e ``?seed=1``
    roda o ``preparar_app`` inteiro (migrações + fixture + admin) — úteis em
    serverless, onde não há shell.

    Nenhum passo pode derrubar a resposta: no Postgres uma exceção deixa a
    transação abortada e toda consulta seguinte falha em cascata, então cada
    etapa é isolada e a conexão é reciclada depois de um erro. Sem isso o
    endpoint devolvia uma página de erro genérica justamente quando havia um
    traceback interessante para mostrar.
    """
    if not _ops_token_ok(request):
        return JsonResponse({'status': 'ok'})

    import io
    import traceback
    from django.core.management import call_command
    from django.db import connection, connections

    info = {
        'engine': connection.vendor,
        'preparar_no_boot': os.environ.get('PREPARAR_APP_NO_BOOT', ''),
    }

    def _passo(rotulo, fn):
        """Roda fn, guarda o resultado ou o traceback e nunca propaga."""
        try:
            info[rotulo] = fn()
        except Exception:
            info[rotulo] = 'erro'
            info[f'{rotulo}_traceback'] = traceback.format_exc()[-3000:]
            connections.close_all()

    def _contagens():
        from django.contrib.auth.models import User
        return {
            'users': User.objects.count(),
            'constituintes': Constituinte.objects.count(),
            'migracoes_pendentes': _pendentes(),
        }

    def _pendentes():
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connections['default'])
        plano = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return [f'{m.app_label}.{m.name}' for m, _ in plano]

    _passo('estado', _contagens)

    def _rodar(comando, **kwargs):
        buf = io.StringIO()

        def _fn():
            call_command(comando, stdout=buf, stderr=buf, **kwargs)
            return 'ok'
        return _fn, buf

    for param, comando, kwargs in (
        ('migrate', 'migrate', {'interactive': False}),
        ('seed', 'preparar_app', {}),
    ):
        if request.GET.get(param) == '1':
            fn, buf = _rodar(comando, **kwargs)
            _passo(param, fn)
            info[f'{param}_out'] = buf.getvalue()[-1500:]
            _passo('estado_depois', _contagens)

    return JsonResponse(info)


@csrf_exempt
def criar_usuario(request):
    """
    Cria (ou redefine a senha de) um usuário comum — nunca staff/superuser.
    Protegido pelo header ``X-Seed-Token`` igual ao OPS_TOKEN; uso operacional
    em serverless, onde não há shell para gerenciar usuários.
    """
    if request.method != 'POST' or not _ops_token_ok(request):
        return JsonResponse({'erro': 'não autorizado'}, status=403)

    from django.contrib.auth.models import User
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    if not username or len(password) < 8:
        return JsonResponse({'erro': 'username e password (mínimo 8 caracteres) são obrigatórios'},
                            status=400)

    user, novo = User.objects.get_or_create(username=username)
    user.is_staff = False
    user.is_superuser = False
    user.set_password(password)
    user.save()
    return JsonResponse({'usuario': username, 'criado': novo})


def escopo_por_dono(user, qs):
    """
    Restringe o queryset ao que o usuário criou (``created_by``); o
    superusuário vê tudo. Base do isolamento entre contas de terceiros.
    """
    if user.is_superuser:
        return qs
    return qs.filter(created_by=user)


class DonoQuerysetMixin:
    """Limita views de detalhe/edição aos objetos do próprio usuário."""

    def get_queryset(self):
        return escopo_por_dono(self.request.user, super().get_queryset())


class QuerystringMixin:
    """
    Disponibiliza ``querystring`` no contexto — os parâmetros de filtro da URL
    sem o ``page``. Permite paginar preservando busca e filtros aplicados.
    """

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop('page', None)
        ctx['querystring'] = params.urlencode()
        return ctx


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardView(LoginRequiredMixin, ListView):
    model = Produto
    template_name = 'rotulagem/dashboard.html'
    context_object_name = 'produtos'

    def get_queryset(self):
        qs = escopo_por_dono(self.request.user, Produto.objects.filter(ativo=True))
        return qs.prefetch_related('grupos_populacionais', 'formulacao').order_by('-updated_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Quick conformity check for each product
        try:
            lista = ListaRegulatoria.objects.get(vigente=True)
        except ListaRegulatoria.DoesNotExist:
            lista = None

        conformity = {}
        for produto in ctx['produtos']:
            if not produto.formulacao.exists():
                conformity[produto.pk] = 'sem_dados'
                continue

            if produto.is_alimento:
                itens = produto.formulacao.select_related('materia_prima')
                com_composicao = [
                    hasattr(i.materia_prima, 'composicao') for i in itens
                ]
                if all(com_composicao):
                    conformity[produto.pk] = 'conforme'
                elif any(com_composicao):
                    conformity[produto.pk] = 'parcial'
                else:
                    conformity[produto.pk] = 'sem_dados'
                continue

            grupos = list(produto.grupos_populacionais.all())
            if not grupos or not lista:
                conformity[produto.pk] = 'sem_dados'
                continue
            try:
                motor = MotorCalculo(produto, grupos[0], lista)
                violacoes = motor.validar_conformidade()
                statuses = {v['status'] for v in violacoes}
                if 'acima_maximo' in statuses or 'abaixo_minimo' in statuses:
                    conformity[produto.pk] = 'nao_conforme'
                elif 'sem_limite' in statuses:
                    conformity[produto.pk] = 'parcial'
                else:
                    conformity[produto.pk] = 'conforme'
            except Exception:
                conformity[produto.pk] = 'erro'

        ctx['conformity'] = conformity
        ctx['lista_vigente'] = lista
        ctx['total_produtos'] = escopo_por_dono(
            self.request.user, Produto.objects.filter(ativo=True)).count()
        ctx['total_materias'] = escopo_por_dono(
            self.request.user, MateriaPrima.objects.filter(ativo=True)).count()
        ctx['total_constituintes'] = Constituinte.objects.filter(autorizado=True).count()
        return ctx


# ---------------------------------------------------------------------------
# Produto CRUD
# ---------------------------------------------------------------------------

class ProdutoListView(LoginRequiredMixin, QuerystringMixin, ListView):
    model = Produto
    template_name = 'rotulagem/produto_list.html'
    context_object_name = 'produtos'
    paginate_by = 20

    def get_queryset(self):
        qs = escopo_por_dono(
            self.request.user, Produto.objects.prefetch_related('grupos_populacionais'))
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(nome__icontains=q) | qs.filter(marca__icontains=q)
        ativo = self.request.GET.get('ativo', '1')
        if ativo == '1':
            qs = qs.filter(ativo=True)
        return qs.order_by('nome')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ProdutoCreateView(LoginRequiredMixin, CreateView):
    model = Produto
    form_class = ProdutoForm
    template_name = 'rotulagem/produto_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f'Produto "{self.object.nome}" criado com sucesso.')
        return response

    def get_success_url(self):
        return reverse('rotulagem:produto_formulacao', kwargs={'pk': self.object.pk})


class ProdutoUpdateView(LoginRequiredMixin, DonoQuerysetMixin, UpdateView):
    model = Produto
    form_class = ProdutoForm
    template_name = 'rotulagem/produto_form.html'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Produto "{self.object.nome}" atualizado.')
        return response

    def get_success_url(self):
        return reverse('rotulagem:produto_detail', kwargs={'pk': self.object.pk})


class ProdutoDetailView(LoginRequiredMixin, DonoQuerysetMixin, DetailView):
    model = Produto
    template_name = 'rotulagem/produto_detail.html'
    context_object_name = 'produto'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['formulacao'] = self.object.formulacao.select_related(
            'materia_prima__constituinte'
        ).order_by('ordem')
        ctx['grupos'] = self.object.grupos_populacionais.all()
        ctx['versoes'] = self.object.versoes.all()[:5]
        return ctx


# ---------------------------------------------------------------------------
# Formulação HTMX editor
# ---------------------------------------------------------------------------

class ProdutoFormulacaoView(LoginRequiredMixin, DonoQuerysetMixin, UpdateView):
    model = Produto
    form_class = ProdutoForm
    template_name = 'rotulagem/produto_formulacao.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx['formulacao_formset'] = FormulacaoItemFormSet(
                self.request.POST, instance=self.object,
                form_kwargs={'user': self.request.user},
            )
        else:
            ctx['formulacao_formset'] = FormulacaoItemFormSet(
                instance=self.object, form_kwargs={'user': self.request.user})
        ctx['materias_primas'] = escopo_por_dono(
            self.request.user, MateriaPrima.objects.filter(ativo=True)
        ).select_related('constituinte').order_by('nome_comercial')
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx['formulacao_formset']

        if formset.is_valid():
            # Snapshot current version before saving
            _salvar_versao(self.object, self.request.user, 'Atualização via formulário')

            self.object = form.save()
            self.object.versao_atual += 1
            self.object.save(update_fields=['versao_atual'])
            formset.instance = self.object
            formset.save()
            messages.success(self.request, 'Formulação salva com sucesso.')
            return redirect(reverse('rotulagem:produto_detail', kwargs={'pk': self.object.pk}))
        else:
            return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('rotulagem:produto_detail', kwargs={'pk': self.object.pk})


def _salvar_versao(produto, usuario, motivo=''):
    """Cria um snapshot VersaoProduto antes de qualquer modificação."""
    snapshot = {
        'produto': {
            'nome': produto.nome,
            'marca': produto.marca,
            'forma_apresentacao': produto.forma_apresentacao,
            'unidades_por_dose': float(produto.unidades_por_dose),
            'doses_por_embalagem': produto.doses_por_embalagem,
        },
        'formulacao': [
            {
                'materia_prima': item.materia_prima.nome_comercial,
                'materia_prima_id': item.materia_prima.pk,
                'quantidade_g': float(item.quantidade_g),
                'overage_pct': float(item.overage_pct),
                'ordem': item.ordem,
            }
            for item in produto.formulacao.select_related('materia_prima')
        ],
    }
    VersaoProduto.objects.create(
        produto=produto,
        versao_numero=produto.versao_atual,
        snapshot_json=snapshot,
        motivo=motivo,
        created_by=usuario,
    )


# ---------------------------------------------------------------------------
# HTMX: add/remove formulation items inline
# ---------------------------------------------------------------------------

class FormulacaoItemAddView(LoginRequiredMixin, View):
    """HTMX endpoint: add a FormulacaoItem and return updated row partial."""

    def post(self, request, produto_pk):
        produto = get_object_or_404(
            escopo_por_dono(request.user, Produto.objects.all()), pk=produto_pk)
        mp_id = request.POST.get('materia_prima')
        quantidade = request.POST.get('quantidade_g', '0')
        overage = request.POST.get('overage_pct', '0')

        if not mp_id:
            return HttpResponse('<div class="alert alert-warning">Selecione uma matéria-prima.</div>')

        mp = get_object_or_404(
            escopo_por_dono(request.user, MateriaPrima.objects.filter(ativo=True)), pk=mp_id)
        ordem = produto.formulacao.count()
        item = FormulacaoItem.objects.create(
            produto=produto,
            materia_prima=mp,
            quantidade_g=quantidade,
            overage_pct=overage,
            ordem=ordem,
        )

        response = render(request, 'rotulagem/partials/formulacao_row.html', {'item': item})
        response['HX-Trigger'] = 'formulacaoUpdated'
        return response


class FormulacaoItemDeleteView(LoginRequiredMixin, View):
    """HTMX endpoint: delete a FormulacaoItem and return empty."""

    def delete(self, request, pk):
        qs = FormulacaoItem.objects.all()
        if not request.user.is_superuser:
            qs = qs.filter(produto__created_by=request.user)
        item = get_object_or_404(qs, pk=pk)
        item.delete()
        response = HttpResponse('')
        response['HX-Trigger'] = 'formulacaoUpdated'
        return response


# ---------------------------------------------------------------------------
# Cálculo nutricional
# ---------------------------------------------------------------------------

class ProdutoCalculoView(LoginRequiredMixin, View):
    template_name = 'rotulagem/calculo.html'

    def get(self, request, pk):
        produto = get_object_or_404(
            escopo_por_dono(request.user, Produto.objects.all()), pk=pk)

        if produto.is_alimento:
            return self._calculo_alimento(request, produto)

        form = CalculoFiltroForm(request.GET or None)
        ctx = {
            'produto': produto,
            'form': form,
            'resultado': None,
            'grupo': None,
            'lista': None,
        }

        if form.is_valid():
            grupo = form.cleaned_data['grupo_populacional']
            lista = form.cleaned_data.get('lista_regulatoria') or None

            try:
                motor = MotorCalculo(produto, grupo, lista)
                resultado = motor.calcular_por_dose()
                lista_usada = motor.lista

                # Persist log
                CalculoLog.objects.create(
                    produto=produto,
                    usuario=request.user,
                    lista_regulatoria_usada=lista_usada,
                    resultado_json=resultado,
                    grupos_calculados=[grupo.nome],
                )

                ctx['resultado'] = resultado
                ctx['grupo'] = grupo
                ctx['lista'] = lista_usada
                ctx['resultado_items'] = list(resultado.items())

            except ValueError as e:
                messages.error(request, str(e))

        return render(request, self.template_name, ctx)

    def _calculo_alimento(self, request, produto):
        """Cálculo RDC 429/2020 + IN 75/2020 — sem grupo populacional (VD adulto)."""
        ctx = {
            'produto': produto,
            'form': None,
            'resultado': None,
            'resultado_alimento': None,
            'grupo': None,
            'lista': None,
        }
        try:
            motor = MotorCalculoAlimento(produto)
            resultado = motor.calcular()

            CalculoLog.objects.create(
                produto=produto,
                usuario=request.user,
                lista_regulatoria_usada=motor.lista,
                resultado_json=resultado,
                grupos_calculados=['Alimentos — VD dieta 2.000 kcal'],
            )

            ctx['resultado_alimento'] = resultado
            ctx['lista'] = motor.lista
        except ValueError as e:
            messages.error(request, str(e))

        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# Relatório de conformidade QA
# ---------------------------------------------------------------------------

class ProdutoRelatorioView(LoginRequiredMixin, View):
    template_name = 'rotulagem/relatorio_qa.html'

    def get(self, request, pk):
        produto = get_object_or_404(
            escopo_por_dono(request.user, Produto.objects.all()), pk=pk)

        if produto.is_alimento:
            return self._relatorio_alimento(request, produto)

        grupos = list(produto.grupos_populacionais.all())

        try:
            lista = ListaRegulatoria.objects.get(vigente=True)
        except ListaRegulatoria.DoesNotExist:
            messages.error(request, 'Nenhuma lista regulatória vigente configurada.')
            return redirect(reverse('rotulagem:produto_detail', kwargs={'pk': pk}))

        relatorio = {}
        totais = {'ok': 0, 'abaixo_minimo': 0, 'acima_maximo': 0, 'sem_limite': 0}

        for grupo in grupos:
            try:
                motor = MotorCalculo(produto, grupo, lista)
                violacoes = motor.validar_conformidade()
                relatorio[grupo.nome] = violacoes
                for v in violacoes:
                    totais[v['status']] = totais.get(v['status'], 0) + 1
            except Exception as e:
                relatorio[grupo.nome] = [{'status': 'erro', 'mensagem': str(e), 'constituinte': 'Erro'}]

        ctx = {
            'produto': produto,
            'relatorio': relatorio,
            'grupos': grupos,
            'lista': lista,
            'totais': totais,
            'aprovado': totais['abaixo_minimo'] == 0 and totais['acima_maximo'] == 0,
        }
        return render(request, self.template_name, ctx)

    def _relatorio_alimento(self, request, produto):
        """Relatório de completude e rotulagem frontal para alimentos."""
        try:
            motor = MotorCalculoAlimento(produto)
            resultado = motor.calcular()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(reverse('rotulagem:produto_detail', kwargs={'pk': produto.pk}))

        ctx = {
            'produto': produto,
            'lista': motor.lista,
            'relatorio_alimento': resultado,
            'aprovado': not resultado['avisos'],
        }
        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# Preview do rótulo
# ---------------------------------------------------------------------------

class ProdutoRotuloView(LoginRequiredMixin, View):
    template_name = 'rotulagem/rotulo_preview.html'

    def get(self, request, pk):
        produto = get_object_or_404(
            escopo_por_dono(request.user, Produto.objects.all()), pk=pk)
        grupos = list(produto.grupos_populacionais.all())

        if not produto.formulacao.exists():
            messages.warning(request, 'Produto sem formulação cadastrada.')
            return redirect(reverse('rotulagem:produto_formulacao', kwargs={'pk': pk}))

        if not produto.is_alimento and not grupos:
            messages.warning(request, 'Produto sem grupos populacionais definidos.')
            return redirect(reverse('rotulagem:produto_detail', kwargs={'pk': pk}))

        try:
            if produto.is_alimento:
                rotulo = GeradorRotuloAlimento(produto).gerar()
            else:
                rotulo = GeradorRotulo(produto, grupos).gerar()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(reverse('rotulagem:produto_detail', kwargs={'pk': pk}))

        ctx = {
            'produto': produto,
            'rotulo': rotulo,
            'grupos': grupos,
        }
        return render(request, self.template_name, ctx)


# ---------------------------------------------------------------------------
# Impressão / PDF export
# ---------------------------------------------------------------------------

def _montar_rotulo(request, pk):
    """
    Valida o produto e gera o rótulo. Retorna ``((produto, rotulo, grupos), None)``
    ou ``(None, redirect)`` quando o produto está incompleto ou o cálculo falha.
    """
    produto = get_object_or_404(
        escopo_por_dono(request.user, Produto.objects.all()), pk=pk)
    grupos = list(produto.grupos_populacionais.all())

    if not produto.formulacao.exists() or (not produto.is_alimento and not grupos):
        messages.error(request, 'Produto incompleto — adicione grupos e formulação.')
        return None, redirect(reverse('rotulagem:produto_detail', kwargs={'pk': pk}))

    try:
        if produto.is_alimento:
            rotulo = GeradorRotuloAlimento(produto).gerar()
        else:
            rotulo = GeradorRotulo(produto, grupos).gerar()
    except ValueError as e:
        messages.error(request, str(e))
        return None, redirect(reverse('rotulagem:produto_detail', kwargs={'pk': pk}))

    return (produto, rotulo, grupos), None


class ProdutoImprimirView(LoginRequiredMixin, View):
    """
    Versão imprimível do rótulo — o usuário salva como PDF pelo diálogo de
    impressão do navegador. Não depende do WeasyPrint, então funciona em
    ambientes sem as bibliotecas nativas (ex.: serverless/Vercel).
    """

    def get(self, request, pk):
        dados, erro = _montar_rotulo(request, pk)
        if erro:
            return erro
        produto, rotulo, grupos = dados
        return render(request, 'rotulagem/rotulo_pdf.html', {
            'produto': produto,
            'rotulo': rotulo,
            'grupos': grupos,
            'modo_impressao': True,
        })


class ProdutoExportarPDFView(LoginRequiredMixin, View):

    def get(self, request, pk):
        dados, erro = _montar_rotulo(request, pk)
        if erro:
            return erro
        produto, rotulo, grupos = dados

        # Render HTML template
        html_string = render(
            request,
            'rotulagem/rotulo_pdf.html',
            {'produto': produto, 'rotulo': rotulo, 'grupos': grupos},
        ).content.decode('utf-8')

        try:
            from weasyprint import HTML, CSS
            pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
        except ImportError:
            return HttpResponse(
                'WeasyPrint não está instalado. Execute: pip install WeasyPrint',
                status=500,
            )
        except OSError as e:
            return HttpResponse(
                'WeasyPrint não encontrou as bibliotecas nativas (pango/gobject). '
                'No macOS: brew install pango. Detalhe: ' + str(e),
                status=500,
            )

        filename = f'rotulo_{produto.nome}_{timezone.now().strftime("%Y%m%d")}.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Matérias-Primas CRUD
# ---------------------------------------------------------------------------

class MateriaPrimaListView(LoginRequiredMixin, QuerystringMixin, ListView):
    model = MateriaPrima
    template_name = 'rotulagem/materia_prima_list.html'
    context_object_name = 'materias'
    paginate_by = 30

    def get_queryset(self):
        qs = escopo_por_dono(
            self.request.user,
            MateriaPrima.objects.select_related('constituinte').filter(ativo=True))
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(nome_comercial__icontains=q)
        tipo = self.request.GET.get('tipo', '')
        if tipo:
            qs = qs.filter(constituinte__tipo=tipo)
        return qs.order_by('nome_comercial')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['tipo_filtro'] = self.request.GET.get('tipo', '')
        from .models import TIPO_CONSTITUINTE
        ctx['tipos'] = TIPO_CONSTITUINTE
        return ctx


class ComposicaoFormMixin:
    """Acopla o formulário de composição nutricional (por 100 g) às telas de MP."""

    def _composicao_instance(self):
        obj = getattr(self, 'object', None)
        return getattr(obj, 'composicao', None) if obj else None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'composicao_form' not in ctx:
            ctx['composicao_form'] = ComposicaoNutricionalForm(
                instance=self._composicao_instance()
            )
        return ctx

    def form_valid(self, form):
        composicao_form = ComposicaoNutricionalForm(
            self.request.POST, instance=self._composicao_instance()
        )
        if not composicao_form.is_valid():
            return self.render_to_response(
                self.get_context_data(form=form, composicao_form=composicao_form)
            )
        response = super().form_valid(form)
        # Só cria a composição se algo foi preenchido (MPs de suplemento podem não ter)
        if composicao_form.instance.pk or composicao_form.has_changed():
            composicao = composicao_form.save(commit=False)
            composicao.materia_prima = self.object
            composicao.save()
        return response


class MateriaPrimaCreateView(LoginRequiredMixin, ComposicaoFormMixin, CreateView):
    model = MateriaPrima
    form_class = MateriaPrimaForm
    template_name = 'rotulagem/materia_prima_form.html'
    success_url = reverse_lazy('rotulagem:materia_prima_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Matéria-prima cadastrada com sucesso.')
        return super().form_valid(form)


class MateriaPrimaUpdateView(LoginRequiredMixin, DonoQuerysetMixin, ComposicaoFormMixin, UpdateView):
    model = MateriaPrima
    form_class = MateriaPrimaForm
    template_name = 'rotulagem/materia_prima_form.html'
    success_url = reverse_lazy('rotulagem:materia_prima_list')

    def form_valid(self, form):
        messages.success(self.request, 'Matéria-prima atualizada.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Constituintes (view only — managed via Admin for regulatory data)
# ---------------------------------------------------------------------------

class ConstituinteListView(LoginRequiredMixin, QuerystringMixin, ListView):
    model = Constituinte
    template_name = 'rotulagem/constituinte_list.html'
    context_object_name = 'constituintes'
    paginate_by = 50

    def get_queryset(self):
        qs = Constituinte.objects.select_related(
            'lista_regulatoria'
        ).filter(autorizado=True)
        tipo = self.request.GET.get('tipo', '')
        if tipo:
            qs = qs.filter(tipo=tipo)
        lista = self.request.GET.get('lista', '')
        if lista:
            qs = qs.filter(lista_regulatoria_id=lista)
        q = self.request.GET.get('q', '')
        if q:
            qs = qs.filter(nome__icontains=q)
        return qs.order_by('tipo', 'nome')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .models import TIPO_CONSTITUINTE
        ctx['tipos'] = TIPO_CONSTITUINTE
        ctx['tipo_filtro'] = self.request.GET.get('tipo', '')
        ctx['q'] = self.request.GET.get('q', '')
        ctx['listas'] = ListaRegulatoria.objects.all()
        ctx['lista_filtro'] = self.request.GET.get('lista', '')
        return ctx


# ---------------------------------------------------------------------------
# HTMX: quick nutrient lookup for formulation editor
# ---------------------------------------------------------------------------

class NutrienteInfoView(LoginRequiredMixin, View):
    """Returns constituent info when a matéria-prima is selected (HTMX)."""

    def get(self, request):
        mp_id = request.GET.get('mp_id')
        if not mp_id:
            return HttpResponse('')
        try:
            mp = escopo_por_dono(
                request.user, MateriaPrima.objects.select_related('constituinte')).get(pk=mp_id)
            ctx = {'mp': mp}
            return render(request, 'rotulagem/partials/nutriente_info.html', ctx)
        except MateriaPrima.DoesNotExist:
            return HttpResponse('')
