"""
importador_in28.py — Importação da lista de constituintes da IN 28/2018
========================================================================

Lê a tabela ``powerbi_constituintes`` do banco do dashboard de OPs
(lotes_manuais.db) e popula as tabelas regulatórias do Rótulo Fácil:

    Constituinte           ← coluna "Nutriente/Substância Bioativa/Enzima"
    FonteAutorizada        ← coluna "Constituintes Autorizados" (+ CAS, função…)
    LimiteConstituinte     ← colunas de faixa etária (8 grupos populacionais)
    AlegacaoAutorizada     ← coluna "Alegações autorizadas…"
    AdvertenciaObrigatoria ← coluna "Requisitos de Rotulagem Complementar…"

IMPORTANTE — esta tabela traz **limites mínimos e máximos**, não IDR.
Os valores de IDR usados no cálculo de %VD vêm da RDC 269/2005
(ver ``seed_idr_rdc269``).

Nenhum valor regulatório é hardcoded aqui: tudo é lido do banco de origem
e gravado com vínculo a uma ListaRegulatoria versionada.
"""

import json
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

# ---------------------------------------------------------------------------
# Localização do banco de origem
# ---------------------------------------------------------------------------

CAMINHOS_PADRAO = [
    Path.home() / 'Library/Application Support/lotes-dashboard/lotes_manuais.db',
    Path.home() / 'Apps/lotes-dashboard/lotes_manuais.db',
    Path.home() / 'Apps/lotes-dashboard-v2/lotes_manuais.db',
]


def localizar_banco(caminho_explicito=None) -> Path:
    """Retorna o caminho do lotes_manuais.db, ou levanta FileNotFoundError."""
    if caminho_explicito:
        p = Path(caminho_explicito).expanduser()
        if not p.exists():
            raise FileNotFoundError(f'Banco não encontrado: {p}')
        return p
    for p in CAMINHOS_PADRAO:
        if p.exists():
            return p
    raise FileNotFoundError(
        'lotes_manuais.db não encontrado. Caminhos testados:\n  '
        + '\n  '.join(str(p) for p in CAMINHOS_PADRAO)
        + '\nInforme o caminho com --banco=/caminho/para/lotes_manuais.db'
    )


# ---------------------------------------------------------------------------
# Mapeamentos
# ---------------------------------------------------------------------------

# Índice da coluna no array "linhas" → definição do grupo populacional
GRUPOS_ANVISA = [
    (4,  'Lactentes 0 a 6 meses',     0,  0,  'Lactentes de 0 a 6 meses de idade'),
    (5,  'Lactentes 7 a 11 meses',    0,  0,  'Lactentes de 7 a 11 meses de idade'),
    (6,  'Crianças 1 a 3 anos',       1,  3,  'Crianças de 1 a 3 anos'),
    (7,  'Crianças 4 a 8 anos',       4,  8,  'Crianças de 4 a 8 anos'),
    (8,  'Crianças e adolescentes 9 a 18 anos', 9, 18, 'Crianças e adolescentes de 9 a 18 anos'),
    (9,  'Adultos maiores de 19 anos', 19, None, 'Adultos com 19 anos ou mais'),
    (10, 'Gestantes',                 None, None, 'Mulheres grávidas'),
    (11, 'Lactantes',                 None, None, 'Mulheres em fase de amamentação'),
]

# Categoria ANVISA → tipo do Constituinte
MAPA_TIPO = {
    'aminoácidos':          'aminoacido',
    'aminoacidos':          'aminoacido',
    'minerais':             'mineral',
    'vitaminas':            'vitamina',
    'substâncias bioativas': 'bioativo',
    'substancias bioativas': 'bioativo',
    'lipídeos':             'acido_graxo',
    'lipideos':             'acido_graxo',
    'probióticos':          'probiotico',
    'probioticos':          'probiotico',
    'proteínas':            'proteina',
    'proteinas':            'proteina',
    'enzimas':              'enzima',
    'fibras alimentares':   'outro',
    'carboidratos':         'outro',
    'outros nutrientes':    'outro',
}

# Frases que indicam ausência de alegação autorizada
SEM_ALEGACAO = [
    'não autorizada alegação',
    'nao autorizada alegacao',
    'não foi aprovada alegação',
    'nao foi aprovada alegacao',
    'não há alegação',
    'sem alegação',
]

VALORES_VAZIOS = {'', '-', '--', 'n/a', 'na', 'nao estabelecido', 'não estabelecido', 'none'}


# ---------------------------------------------------------------------------
# Parser de limites
# ---------------------------------------------------------------------------

# "Mínimo: 1.534,67 mg", "Mínimo 4 x 10^9 UFC/dia", "Máximo : não estabelecido"
RE_MINIMO = re.compile(r'm[íi]nimo\s*:?\s*(.+?)(?=m[áa]ximo|$)', re.I | re.S)
RE_MAXIMO = re.compile(r'm[áa]ximo\s*:?\s*(.+?)$', re.I | re.S)

# Número + unidade, incluindo notação científica "1 x 10^9" e "1,5 × 10^10"
RE_VALOR = re.compile(
    r'([\d][\d.,]*)'                        # número base (pt-BR)
    r'(?:\s*[x×X]\s*10\s*\^?\s*(\d+))?'      # opcional: × 10^n
    r'\s*'
    r'(?:[x×X]\s+)?'                         # "190x FTU" — x solto é separador
    r'([^\s\d,;.\n][^\s\n]*(?:/dia)?)?',     # unidade
    re.I,
)


# Expoentes em Unicode usados na planilha da ANVISA: "1 × 10⁹ UFC"
SOBRESCRITOS = {
    '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4',
    '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
    'ꝰ': '9',   # variante encontrada na fonte
}
RE_SOBRESCRITO = re.compile('[' + ''.join(SOBRESCRITOS) + ']+')


def _normalizar_expoentes(txt: str) -> str:
    """'1 × 10⁹ UFC' → '1 x 10^9 UFC' para o RE_VALOR conseguir ler.

    Só converte caracteres realmente sobrescritos — números comuns
    como "105 mg" permanecem intactos.
    """
    if not txt:
        return txt
    t = txt.replace('×', 'x')
    return RE_SOBRESCRITO.sub(
        lambda m: '^' + ''.join(SOBRESCRITOS[c] for c in m.group(0)), t
    )


def _num_ptbr(txt: str):
    """'1.534,67' → Decimal('1534.67'); '180' → Decimal('180'); None se inválido."""
    if not txt:
        return None
    t = txt.strip().replace(' ', '')
    # pt-BR: ponto = milhar, vírgula = decimal
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    else:
        # Só é separador de milhar se houver 3 dígitos após cada ponto
        if re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
            t = t.replace('.', '')
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def _limpar_unidade(u: str) -> str:
    """Normaliza a unidade: remove '/dia', '/porção', pontuação solta, µ→mc."""
    if not u:
        return ''
    u = u.strip().strip('.,;:()')
    u = re.sub(r'/\s*(dia|por[çc][ãa]o|dose|c[áa]psula)?\s*$', '', u, flags=re.I)
    u = u.replace('μ', 'mc').replace('µ', 'mc')  # μg / µg → mcg
    u = u.strip(' /.,;:')
    baixo = u.lower()
    if baixo in ('ufc', 'ufc/dia'):
        return 'UFC'
    if baixo.startswith('esporo'):
        return 'esporos'
    return u.strip()


def _extrair_valor(trecho: str):
    """
    Extrai (valor, unidade) de um trecho como '1.534,67 mg' ou '4 x 10^9 UFC'.
    Retorna (None, '') quando o texto indica ausência de limite.
    """
    if not trecho:
        return None, ''
    t = _normalizar_expoentes(trecho)
    t = re.sub(r'\s+', ' ', t).strip().strip(':').strip()
    if not t or t.lower().strip('.') in VALORES_VAZIOS:
        return None, ''
    if re.search(r'n[ãa]o\s+(estabelecid|autorizad|aplic)', t, re.I):
        return None, ''

    m = RE_VALOR.search(t)
    if not m:
        return None, ''

    base = _num_ptbr(m.group(1))
    if base is None:
        return None, ''
    if m.group(2):                       # notação científica: × 10^n
        base = base * (Decimal(10) ** int(m.group(2)))
    unidade = _limpar_unidade(m.group(3) or '')
    # Se a unidade veio vazia mas há notação científica, assume UFC (probióticos)
    if not unidade and m.group(2):
        unidade = 'UFC'
    return base, unidade


def parse_limite(texto: str) -> dict:
    """
    Interpreta uma célula de limite da IN 28.

    Retorna dict com:
        autorizado (bool), minimo (Decimal|None), maximo (Decimal|None),
        unidade (str), multiplo (bool), bruto (str)

    ``multiplo=True`` indica célula com vários nutrientes (ex.: bloco de
    Lipídeos com ácido linoleico e alfa-linolênico) — nesse caso só o
    primeiro bloco é parseado e o texto completo fica em ``bruto``.
    """
    bruto = (texto or '').strip()
    vazio = {'autorizado': False, 'minimo': None, 'maximo': None,
             'unidade': '', 'multiplo': False, 'bruto': bruto}

    if not bruto or bruto.lower().strip('.') in VALORES_VAZIOS:
        return vazio
    if re.match(r'^\s*n[ãa]o\s+autorizad', bruto, re.I):
        return vazio

    multiplo = len(re.findall(r'm[íi]nimo', bruto, re.I)) > 1

    m_min = RE_MINIMO.search(bruto)
    m_max = RE_MAXIMO.search(bruto)

    minimo, un_min = _extrair_valor(m_min.group(1)) if m_min else (None, '')
    maximo, un_max = _extrair_valor(m_max.group(1)) if m_max else (None, '')

    if minimo is None and maximo is None:
        return vazio

    return {
        'autorizado': True,
        'minimo': minimo,
        'maximo': maximo,
        'unidade': un_min or un_max or '',
        'multiplo': multiplo,
        'bruto': bruto,
    }


def normalizar_nutriente(nome: str) -> str:
    """'Fonte de Cálcio' → 'Cálcio'; 'Aminoácido Lisina' → 'Lisina'."""
    n = re.sub(r'\s+', ' ', (nome or '')).strip()
    if not n:
        return ''

    # "Fonte de probiótico em suplementos alimentares" é rótulo genérico:
    # colapsaria dezenas de cepas distintas num único constituinte.
    # Retorna vazio para que o chamador use o nome da cepa (coluna "Constituintes
    # Autorizados"), preservando um constituinte por linhagem.
    if re.match(r'^fonte\s+d[eo]\s+probi[óo]tico', n, re.I):
        return ''

    # "Fonte do aminoácido X" / "Aminoácido X" → X
    m = re.match(r'^(?:fonte\s+d[eo]\s+)?amino[áa]cido\s+(.+)$', n, re.I)
    if m:
        n = m.group(1)
    else:
        # "Fonte de X" / "Fonte do X" → X
        m = re.match(r'^fonte\s+d[eo]\s+(.+)$', n, re.I)
        if m:
            n = m.group(1)

    n = n.strip(' .,;:')
    return n[:1].upper() + n[1:] if n else ''


def tem_alegacao(texto: str) -> bool:
    if not texto or not texto.strip():
        return False
    t = texto.lower()
    return not any(frase in t for frase in SEM_ALEGACAO)


# ---------------------------------------------------------------------------
# Leitura do banco de origem
# ---------------------------------------------------------------------------

def ler_powerbi_constituintes(caminho_db) -> tuple:
    """Retorna (colunas, linhas, total, atualizado_em) da tabela powerbi_constituintes."""
    conn = sqlite3.connect(f'file:{caminho_db}?mode=ro', uri=True)
    try:
        row = conn.execute(
            'SELECT colunas, linhas, total, atualizado_em FROM powerbi_constituintes'
        ).fetchone()
    except sqlite3.OperationalError as e:
        raise RuntimeError(
            f'Tabela powerbi_constituintes não encontrada em {caminho_db}: {e}'
        ) from e
    finally:
        conn.close()

    if not row:
        raise RuntimeError('Tabela powerbi_constituintes está vazia.')

    return json.loads(row[0]), json.loads(row[1]), row[2], row[3]
