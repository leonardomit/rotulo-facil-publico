# Rótulo Fácil

Sistema de rotulagem de **suplementos alimentares** e **alimentos** conforme a
legislação brasileira (ANVISA):

- **Suplementos** — RDC 243/2018 + IN 28/2018 (tabela por dose, %VD via IDR da
  RDC 269/2005, limites por grupo populacional, alegações e advertências).
  Isentos de rotulagem frontal (RDC 727/2022, Art. 43).
- **Alimentos** — RDC 429/2020 + IN 75/2020 (tabela com dupla declaração por
  porção e por 100 g/100 ml, %VD da dieta de 2.000 kcal e lupa "ALTO EM").

## Início rápido — dois cliques

Requisito único: **Python 3.12+** instalado ([python.org/downloads](https://www.python.org/downloads/)).

| Sistema | Atalho |
|---|---|
| **macOS** | dois cliques em **`iniciar.command`** |
| **Windows** | dois cliques em **`INICIAR-WINDOWS.bat`** (na instalação do Python, marque *"Add Python to PATH"*) |

O atalho instala as dependências, cria o banco, carrega os dados regulatórios,
cria o usuário administrador e abre o app em `http://localhost:5054`.

Usuário inicial: `admin` / senha aleatória, mostrada **uma única vez** no terminal
na primeira execução — anote e troque no primeiro acesso
(Admin → Usuários).

> **macOS:** na primeira vez, se aparecer o aviso de "desenvolvedor não
> identificado", clique com o botão direito em `iniciar.command` → **Abrir** →
> **Abrir** (só é necessário uma vez).

## Instalação manual (qualquer sistema)

Requisitos: Python 3.12+

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # ajuste SECRET_KEY em produção

python manage.py migrate
python manage.py loaddata dados_regulatorios.json
python manage.py createsuperuser
python manage.py runserver
```

### Docker

```bash
docker compose up --build
```

## Dados regulatórios incluídos

O arquivo `rotulagem/fixtures/dados_regulatorios.json` traz as tabelas
regulatórias públicas já estruturadas:

| Conteúdo | Fonte |
|---|---|
| Constituintes, fontes autorizadas, limites mín/máx por grupo populacional, alegações e advertências | IN 28/2018 |
| IDRs (Ingestão Diária de Referência) para %VD de suplementos | RDC 269/2005 |
| Valores Diários (VD) para %VD de alimentos | IN 75/2020 |
| Limites da rotulagem frontal (lupa "ALTO EM") | RDC 429/2020 |

Nenhum dado de produtos, formulações ou matérias-primas acompanha o pacote —
cada empresa cadastra os seus.

Opcional: `python manage.py seed_materias_exemplo` cria matérias-primas de
exemplo (ácido ascórbico, etc.) para explorar o sistema.

## Fluxo de uso

1. **Matérias-Primas** — cadastre suas MPs. Para suplementos, vincule o
   constituinte e o fator de conversão; para alimentos, preencha a
   **composição nutricional por 100 g**.
2. **Produtos** — crie o produto escolhendo a categoria (Suplemento ou
   Alimento) e monte a formulação (g por unidade).
3. **Cálculo** — o sistema gera a tabela nutricional com trilha de auditoria.
4. **Relatório QA** — conformidade com limites (suplementos) ou análise da
   lupa e completude (alimentos).
5. **Rótulo / PDF** — prévia e exportação do rótulo com todos os elementos
   obrigatórios.

## Atualização das listas regulatórias

As listas são versionadas no banco (Admin → Listas Regulatórias). Quando uma
norma mudar, crie uma nova lista/versão — os cálculos registram qual versão
foi usada em cada produto (log de auditoria).

## Notas técnicas

- Banco padrão: SQLite (arquivo `db.sqlite3`, criado no primeiro uso).
  Para PostgreSQL, configure `DATABASE_URL` no `.env`.
- Exportação de PDF usa WeasyPrint. No macOS: `brew install pango`.
  No Docker já funciona sem passos extras.
- Este software auxilia a elaboração de rótulos, mas não substitui a revisão
  por responsável técnico habilitado.
