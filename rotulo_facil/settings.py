import os
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
)

env_file = BASE_DIR / '.env'
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-key-change-in-production')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# Token dos endpoints operacionais (/healthz/); separado da SECRET_KEY para
# que um vazamento do token não permita forjar cookies de sessão.
OPS_TOKEN = env('OPS_TOKEN', default='')

# Atrás do proxy da Vercel a conexão chega como HTTP; o header diz o protocolo
# real. Com isso os cookies podem exigir HTTPS fora do ambiente de dev.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = env('CSRF_TRUSTED_ORIGINS', default=[])

# Atalho para o Regula (controle regulatório) no cabeçalho.
# Vazio = botão não aparece — é o padrão nas cópias distribuídas a terceiros.
REGULA_URL = env('REGULA_URL', default='').strip()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'crispy_forms',
    'crispy_bootstrap5',
    'axes',
    'rotulagem',
]

# django-axes — trava a conta após tentativas seguidas de senha errada.
# Bloqueio por username (não por IP: atrás do proxy da Vercel o REMOTE_ADDR
# é o do proxy). Destrava sozinho após o cooloff ou num login correto.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]
AXES_FAILURE_LIMIT = 6
AXES_COOLOFF_TIME = 0.5  # horas
AXES_LOCKOUT_PARAMETERS = ['username']
AXES_RESET_ON_SUCCESS = True
# axes.W006 sugere travar também por IP, mas atrás do proxy da Vercel o
# REMOTE_ADDR é o do proxy — travar por username é o critério que não se
# contorna com rotação de IP.
SILENCED_SYSTEM_CHECKS = ['axes.W006']

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

ROOT_URLCONF = 'rotulo_facil.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'rotulagem.context_processors.apps_externos',
            ],
        },
    },
]

WSGI_APPLICATION = 'rotulo_facil.wsgi.application'

# Database — SQLite by default, PostgreSQL-ready via DATABASE_URL
_db_url = env('DATABASE_URL', default='')
if _db_url:
    import dj_database_url  # optional dep; falls back to sqlite when not installed
    DATABASES = {'default': dj_database_url.parse(_db_url)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# WhiteNoise serve os estáticos direto do Django — necessário na Vercel, que
# não serve o STATIC_ROOT. USE_FINDERS dispensa o collectstatic no build.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
WHITENOISE_USE_FINDERS = True

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'
