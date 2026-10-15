# Deploy na Vercel

O app está preparado para rodar na Vercel como função serverless Python
(`vercel.json` + alias `app` no `rotulo_facil/wsgi.py`, estáticos via WhiteNoise).

**Atenção:** na Vercel a exportação de PDF pelo servidor (WeasyPrint, rota
`/produtos/<pk>/pdf/`) não funciona — faltam as bibliotecas nativas (Pango/Cairo).
Os botões da interface usam a rota `/produtos/<pk>/imprimir/`, que abre o rótulo
no navegador para imprimir/salvar como PDF e funciona em qualquer ambiente.
Rodando local ou via Docker, a rota `/pdf/` continua disponível.

## Passo a passo

1. **Banco Postgres** (a Vercel não tem disco persistente; SQLite não serve):
   crie um banco gratuito no [Neon](https://neon.tech) ou Supabase e copie a
   connection string (`postgres://...`).

2. **Migrações e seed** — rode da sua máquina apontando para o banco remoto:

   ```bash
   DATABASE_URL='postgres://...' python3 manage.py migrate
   DATABASE_URL='postgres://...' python3 manage.py preparar_app
   ```

3. **Repositório** — suba o projeto para o GitHub (a Vercel faz deploy a partir
   do repo) ou use `vercel deploy` pela CLI.

4. **Projeto na Vercel** — importe o repo em <https://vercel.com/new>. Framework
   preset: "Other". Não precisa de build command.

5. **Variáveis de ambiente** (Settings → Environment Variables):

   | Variável | Valor |
   |---|---|
   | `DEBUG` | `False` |
   | `SECRET_KEY` | gere com `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
   | `ALLOWED_HOSTS` | `.vercel.app` (adicione seu domínio próprio se tiver) |
   | `CSRF_TRUSTED_ORIGINS` | `https://<projeto>.vercel.app` |
   | `DATABASE_URL` | a connection string do passo 1 |
   | `REGULA_URL` | *(opcional)* URL do Regula — cria o botão "Regula" no cabeçalho |

6. **Deploy** e login com o usuário criado pelo `preparar_app`
   (`admin` / a senha aleatória que o comando mostrou — troque no primeiro acesso).

## Limitações conhecidas na Vercel

- Rota `/pdf/` (WeasyPrint) indisponível — use o botão "Imprimir / Salvar PDF".
- Importação da IN 28 (`manage.py importar_in28`) deve ser rodada localmente
  contra o banco remoto, como no passo 2.
