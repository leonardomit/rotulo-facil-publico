#!/bin/bash
# =============================================================
#  Rótulo Fácil — Rotulagem de Suplementos e Alimentos
#  Dê dois cliques neste arquivo para preparar e iniciar o app.
# =============================================================

cd "$(dirname "$0")" || exit 1

PORTA=5054
VERDE='\033[0;32m'; AMARELO='\033[0;33m'; VERMELHO='\033[0;31m'; NC='\033[0m'

echo ""
echo "============================================================"
echo "  Rótulo Fácil — Rotulagem de Suplementos e Alimentos"
echo "============================================================"
echo "  Pasta: $(pwd)"
echo ""

# --- Python -------------------------------------------------
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo -e "${VERMELHO}✗ Python não encontrado.${NC}"
  echo "  Instale em https://www.python.org/downloads/ e rode este arquivo de novo."
  echo ""; read -r -p "Pressione ENTER para fechar..."; exit 1
fi
echo -e "${VERDE}✓${NC} Python: $($PY --version 2>&1)"

# --- Dependências -------------------------------------------
echo ""
echo "→ Verificando dependências..."
if ! $PY -c "import django, environ, dj_database_url, crispy_forms, whitenoise" >/dev/null 2>&1; then
  echo "  Instalando (pode demorar um pouco na primeira vez)..."
  $PY -m pip install -q -r requirements.txt 2>&1 | tail -3
fi
if ! $PY -c "import django, environ, dj_database_url, crispy_forms, whitenoise" >/dev/null 2>&1; then
  echo -e "${VERMELHO}✗ Falha ao instalar dependências.${NC}"
  echo "  Rode manualmente:  $PY -m pip install -r requirements.txt"
  echo ""; read -r -p "Pressione ENTER para fechar..."; exit 1
fi
echo -e "${VERDE}✓${NC} Dependências OK"

# Banco fica na própria pasta do projeto (persiste entre reinícios)
unset DATABASE_URL

# --- Preparação (migrações + dados regulatórios + admin) ----
echo ""
if ! $PY manage.py preparar_app; then
  echo -e "${VERMELHO}✗ Erro ao preparar o banco de dados.${NC}"
  echo ""; read -r -p "Pressione ENTER para fechar..."; exit 1
fi

# --- Servidor -----------------------------------------------
echo ""
echo "============================================================"
echo -e "  ${VERDE}Tudo pronto!${NC}"
echo ""
echo "  Endereço : http://localhost:$PORTA"
echo "  Admin    : http://localhost:$PORTA/admin/"
echo "  Usuário  : admin"
echo "  Senha    : a que apareceu acima na primeira execução"
echo ""
echo "  IMPORTANTE: troque a senha do admin no primeiro acesso."
echo ""
echo "  Para parar o servidor: pressione Control + C"
echo "============================================================"
echo ""

# Abre o navegador assim que o servidor subir
( sleep 3; open "http://localhost:$PORTA" ) &

# 127.0.0.1 = só este Mac. Para abrir na rede local, troque por 0.0.0.0
# e inclua o IP em ALLOWED_HOSTS no .env (com DEBUG=False).
$PY manage.py runserver "127.0.0.1:$PORTA"

echo ""
read -r -p "Servidor encerrado. Pressione ENTER para fechar..."
