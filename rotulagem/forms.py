from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, Field, Div, HTML
from .models import (
    Produto, FormulacaoItem, MateriaPrima, Constituinte,
    GrupoPopulacional, ListaRegulatoria, ALERGENOS_CHOICES,
    ComposicaoNutricional,
)


class ProdutoForm(forms.ModelForm):
    grupos_populacionais = forms.ModelMultipleChoiceField(
        queryset=GrupoPopulacional.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Grupos Populacionais',
        help_text='Obrigatório para suplementos; opcional para alimentos.',
    )

    class Meta:
        model = Produto
        fields = [
            'nome', 'marca', 'categoria', 'denominacao_legal', 'forma_apresentacao',
            'peso_unidade_g', 'volume_unidade_ml',
            'unidades_por_dose', 'doses_por_embalagem',
            'medida_caseira', 'grupos_populacionais', 'ativo',
        ]
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex: Vitamina C 1000mg'}),
            'marca': forms.TextInput(attrs={'placeholder': 'Ex: Sua Marca'}),
            'denominacao_legal': forms.TextInput(
                attrs={'placeholder': 'Ex: Chá verde solúvel em pó'}
            ),
            'medida_caseira': forms.TextInput(attrs={'placeholder': 'Ex: 1 scoop (30 g)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('nome', css_class='col-md-5'),
                Column('marca', css_class='col-md-3'),
                Column('categoria', css_class='col-md-4'),
            ),
            'denominacao_legal',
            Row(
                Column('forma_apresentacao', css_class='col-md-4'),
                Column('peso_unidade_g', css_class='col-md-4'),
                Column('volume_unidade_ml', css_class='col-md-4'),
            ),
            Row(
                Column('unidades_por_dose', css_class='col-md-3'),
                Column('doses_por_embalagem', css_class='col-md-3'),
                Column('medida_caseira', css_class='col-md-6'),
            ),
            Div('grupos_populacionais', css_class='mb-3'),
            Row(
                Column(Field('ativo'), css_class='col-md-2'),
            ),
            Submit('submit', 'Salvar Produto', css_class='btn btn-primary'),
        )

    def clean(self):
        cleaned = super().clean()
        categoria = cleaned.get('categoria')
        if categoria == 'suplemento' and not cleaned.get('grupos_populacionais'):
            self.add_error('grupos_populacionais',
                           'Obrigatório para suplementos alimentares.')
        if categoria == 'alimento':
            if not cleaned.get('peso_unidade_g') and not cleaned.get('volume_unidade_ml'):
                self.add_error(
                    'peso_unidade_g',
                    'Para alimentos informe o peso (g) ou o volume (ml) da unidade — '
                    'necessário para a tabela por 100 g/100 ml.'
                )
        return cleaned


class FormulacaoItemForm(forms.ModelForm):
    class Meta:
        model = FormulacaoItem
        fields = ['materia_prima', 'quantidade_g', 'overage_pct', 'ordem']
        widgets = {
            'materia_prima': forms.Select(attrs={'class': 'form-select select-mp'}),
            'quantidade_g': forms.NumberInput(attrs={
                'step': '0.000001', 'min': '0',
                'class': 'form-control',
                'placeholder': 'g/unidade',
            }),
            'overage_pct': forms.NumberInput(attrs={
                'step': '0.01', 'min': '0', 'max': '100',
                'class': 'form-control',
                'placeholder': '%',
            }),
            'ordem': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = MateriaPrima.objects.filter(
            ativo=True
        ).select_related('constituinte').order_by('nome_comercial')
        if user is not None and not user.is_superuser:
            qs = qs.filter(created_by=user)
        self.fields['materia_prima'].queryset = qs
        self.fields['materia_prima'].label_from_instance = lambda mp: (
            f'{mp.nome_comercial} ({mp.fator_conversao}% {mp.constituinte.nome})'
            if mp.constituinte else mp.nome_comercial
        )


FormulacaoItemFormSet = inlineformset_factory(
    Produto,
    FormulacaoItem,
    form=FormulacaoItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class MateriaPrimaForm(forms.ModelForm):
    alergenos = forms.MultipleChoiceField(
        choices=ALERGENOS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Alérgenos Presentes',
    )

    class Meta:
        model = MateriaPrima
        fields = [
            'nome_comercial', 'nome_cientifico', 'constituinte',
            'fator_conversao', 'unidade_medida', 'fornecedor',
            'forma_quimica', 'alergenos', 'transgenico',
            'aditivo', 'funcao_aditivo', 'ins_aditivo',
            'ativo', 'observacoes',
        ]
        widgets = {
            'nome_comercial': forms.TextInput(attrs={'placeholder': 'Ex: Ácido Ascórbico 99%'}),
            'observacoes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize alergenos from JSON field
        if self.instance.pk:
            self.fields['alergenos'].initial = self.instance.alergenos
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('nome_comercial', css_class='col-md-8'),
                Column('constituinte', css_class='col-md-4'),
            ),
            Row(
                Column('fator_conversao', css_class='col-md-3'),
                Column('unidade_medida', css_class='col-md-2'),
                Column('forma_quimica', css_class='col-md-4'),
                Column('fornecedor', css_class='col-md-3'),
            ),
            'nome_cientifico',
            Div(
                HTML('<h6 class="mt-3">Alérgenos</h6>'),
                'alergenos',
                css_class='mb-3',
            ),
            Row(
                Column(Field('transgenico'), css_class='col-md-2'),
                Column(Field('aditivo'), css_class='col-md-2'),
                Column('funcao_aditivo', css_class='col-md-4'),
                Column('ins_aditivo', css_class='col-md-2'),
                Column(Field('ativo'), css_class='col-md-2'),
            ),
            'observacoes',
        )

    def clean_alergenos(self):
        return self.cleaned_data.get('alergenos', [])


class ComposicaoNutricionalForm(forms.ModelForm):
    """Composição centesimal (por 100 g) da matéria-prima — usada em alimentos."""

    class Meta:
        model = ComposicaoNutricional
        exclude = ['materia_prima']
        widgets = {
            campo: forms.NumberInput(attrs={'step': '0.01', 'min': '0'})
            for campo in [
                'energia_kcal', 'carboidratos_g', 'acucares_totais_g',
                'acucares_adicionados_g', 'proteinas_g', 'gorduras_totais_g',
                'gorduras_saturadas_g', 'gorduras_trans_g', 'fibras_g', 'sodio_mg',
            ]
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('energia_kcal', css_class='col-md-3'),
                Column('carboidratos_g', css_class='col-md-3'),
                Column('acucares_totais_g', css_class='col-md-3'),
                Column('acucares_adicionados_g', css_class='col-md-3'),
            ),
            Row(
                Column('proteinas_g', css_class='col-md-3'),
                Column('gorduras_totais_g', css_class='col-md-3'),
                Column('gorduras_saturadas_g', css_class='col-md-3'),
                Column('gorduras_trans_g', css_class='col-md-3'),
            ),
            Row(
                Column('fibras_g', css_class='col-md-3'),
                Column('sodio_mg', css_class='col-md-3'),
                Column('fonte_dados', css_class='col-md-6'),
            ),
        )


class CalculoFiltroForm(forms.Form):
    grupo_populacional = forms.ModelChoiceField(
        queryset=GrupoPopulacional.objects.all(),
        label='Grupo Populacional',
        empty_label='Selecione um grupo',
    )
    lista_regulatoria = forms.ModelChoiceField(
        queryset=ListaRegulatoria.objects.all(),
        label='Lista Regulatória',
        required=False,
        help_text='Deixe em branco para usar a lista vigente',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set default to vigente lista
        try:
            vigente = ListaRegulatoria.objects.get(vigente=True)
            self.fields['lista_regulatoria'].initial = vigente.pk
        except ListaRegulatoria.DoesNotExist:
            pass
