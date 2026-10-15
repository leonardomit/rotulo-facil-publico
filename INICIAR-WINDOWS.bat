@echo off
chcp 65001 >nul
title Rotulo Facil - Rotulagem de Suplementos e Alimentos
cd /d "%~dp0"

echo.
echo ============================================================
echo   Rotulo Facil - Rotulagem de Suplementos e Alimentos
echo ============================================================
echo   Pasta: %CD%
echo.

rem --- Python -------------------------------------------------
set PY=
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERRO] Python nao encontrado.
  echo Instale em https://www.python.org/downloads/
  echo IMPORTANTE: marque a opcao "Add Python to PATH" na instalacao.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version 2^>^&1') do echo [OK] Python: %%v

rem --- Dependencias -------------------------------------------
echo.
echo - Verificando dependencias...
%PY% -c "import django, environ, dj_database_url, crispy_forms, whitenoise" >nul 2>nul
if errorlevel 1 (
  echo   Instalando... pode demorar um pouco na primeira vez.
  %PY% -m pip install -q -r requirements.txt
)
%PY% -c "import django, environ, dj_database_url, crispy_forms, whitenoise" >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Falha ao instalar dependencias.
  echo Rode manualmente:  %PY% -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)
echo [OK] Dependencias prontas

rem Banco fica na propria pasta do projeto
set DATABASE_URL=

rem --- Preparacao (migracoes + dados regulatorios + admin) ----
echo.
%PY% manage.py preparar_app
if errorlevel 1 (
  echo [ERRO] Falha ao preparar o banco de dados.
  echo.
  pause
  exit /b 1
)

rem --- Servidor -----------------------------------------------
echo.
echo ============================================================
echo   Tudo pronto!
echo.
echo   Endereco : http://localhost:5054
echo   Admin    : http://localhost:5054/admin/
echo   Usuario  : admin
echo   Senha    : a que apareceu acima na primeira execucao
echo.
echo   IMPORTANTE: troque a senha do admin no primeiro acesso.
echo.
echo   Para parar o servidor: feche esta janela ou pressione Ctrl+C
echo ============================================================
echo.

start "" http://localhost:5054
%PY% manage.py runserver 0.0.0.0:5054

echo.
pause
