# union/settings.py
from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab
import os

# =====================================================
# BASE
# =====================================================
BASE_DIR = Path(__file__).resolve().parent.parent

COFRE_VAULT_PIN = os.environ.get("COFRE_VAULT_PIN", None)
# COFRE_MASTER_KEY também precisa
# Exemplo (NÃO deixar fixo):
# COFRE_MASTER_KEY = os.environ.get("COFRE_MASTER_KEY")

COFRE_TIMEOUT_SECONDS = 300        # cofre destrava por 5 min
COFRE_PIN_MAX_TENTATIVAS = 5
COFRE_PIN_BLOQUEIO_SEGUNDOS = 300
BC_BUSCAR_NO_CONTEUDO = True
BC_DIAS_DESATUALIZADO = 365   # padrã

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-f4&(-))drb56ermkqsiro%*dohj)kk(3ysm8ehabfzo(=^q@q7"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS",
    "logicacloud.com.br,union.logicacloud.com.br,192.168.1.109,localhost,127.0.0.1"
).split(",")
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "DJANGO_CSRF_ORIGINS",
    "https://union.logicacloud.com.br,https://logicacloud.com.br"
).split(",")

# =====================================================
# APLICATIVOS
# =====================================================
INSTALLED_APPS = [
    # Django padrão
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_select2",

    # Terceiros
    "ckeditor",
    "ckeditor_uploader",
    "django_extensions",

    # Apps do projeto
    "recompensas",
    "users",
    "sistemas",
    "setup",
    "whatsapp_bot",
    "atendimentos_chamados",
    "clientes_sistemas",
    "base_conhecimento",
    "cofre_senhas",
    "arquivos_instaladores",
    "implantacao",
    "cs_satisfacao",
    "controle_horas.apps.ControleHorasConfig",
    "calendario_agenda.apps.CalendarioAgendaConfig",
    "central_relatorios",
    'crm_vendas',
    'raio_x',
    "assistente_ia",
]


# Uploads
import os
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# =====================================================
# MIDDLEWARE / TEMPLATES / ROOT
# =====================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "union.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": [
                "controle_horas.templatetags.horas_extras",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "union.wsgi.application"

# =====================================================
# BANCO DE DADOS
# =====================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "unionbd"),
        "USER": os.environ.get("DB_USER", "sysdba"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "masterkey"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# =====================================================
# SENHAS / SEGURANÇA
# =====================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =====================================================
# I18N / TIMEZONE
# =====================================================
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


COFRE_VAULT_PIN = "5497"  # provisório, pra testar
COFRE_MASTER_KEY = "T2smkXN-wkcHCQoIEPUkk0jG2iaUbFThbtI1BOF0OSc="  # a que você gerou

# =====================================================
# STATIC / MEDIA
# =====================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================
# CKEDITOR
# =====================================================
CKEDITOR_UPLOAD_PATH = "uploads/"
CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": "full",
        "height": 300,
        "width": "100%",
    }
}

# =====================================================
# CELERY
# =====================================================
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = "America/Sao_Paulo"

CELERY_BEAT_SCHEDULE = {
    "send_event_email_reminders_every_minute": {
        "task": "calendario_agenda.tasks.send_event_email_reminders",
        "schedule": timedelta(minutes=1),
    },
    "send_event_whatsapp_reminders_every_minute": {   # <- renomeei só para ficar simétrico
        "task": "calendario_agenda.tasks.send_event_whatsapp_reminders",
        "schedule": timedelta(minutes=1),             # <- trocado de crontab() para timedelta
    },
}


# SMTP real (como você já testou e funcionou)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "implantacao.logica@gmail.com"
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
EMAIL_TIMEOUT = 30

# =====================================================
# LOGIN / LOGOUT
# =====================================================
LOGIN_URL = '/usuarios/login/'
LOGIN_REDIRECT_URL = '/setup/'  # 🔥 Agora o login te joga pro lugar certo!
LOGOUT_REDIRECT_URL = '/usuarios/login/'

# =====================================================
# WHATSAPP (SESSÃO DE NOTIFICAÇÕES DO UNION)
# =====================================================
import os

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://192.168.1.109:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "EVOapiKey_24xZp9KdY7LfQ2")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "atendimento_suporte")


WHATSAPP_PROVIDER = "evolution"          # ou "wppconnect"
WHATSAPP_SESSION_NAME = "reminders"      # alias para logs/identificação
WHATSAPP_TEST_NUMBER = ""                # opcional, ex.: "55DDDXXXXXXXXX" p/ testes rápidos

# --- Evolution ---
EVOLUTION_BASE_URL = EVOLUTION_API_URL   # ex.: http://127.0.0.1:8080
EVOLUTION_INSTANCE = EVOLUTION_INSTANCE               # nome/instância criada no painel
EVOLUTION_TOKEN = "SEU_TOKEN_DA_INSTANCIA"     # apikey/token da instância

# --- WPPConnect (se usar) ---
# WPPCONNECT_BASE_URL = "http://localhost:21465"
# WPPCONNECT_SESSION  = "reminders"
# WPPCONNECT_TOKEN    = "SEU_TOKEN_BEARER"

# =====================================================
# LIMITES DE UPLOAD (Aumento para evitar RequestDataTooBig)
# =====================================================
# Upload em chunks do hub de instaladores: cada pedaço tem 5MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024   # 6MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024   # 6MB

# ==============================================================================
# CAIXA PRETA: RASTREADOR DE DUPLICIDADES DO WHATSAPP
# ==============================================================================
import os

# Certifique-se de que a pasta 'logs' existe, ou ele criará o arquivo na raiz
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detalhado': {
            'format': '{levelname} | {asctime} | {module} | {message}',
            'style': '{',
        },
    },
    'handlers': {
        'arquivo_whatsapp': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'whatsapp_bot_debug.log'),
            'formatter': 'detalhado',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'rastreador_zap': {
            'handlers': ['arquivo_whatsapp'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
