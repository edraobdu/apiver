SECRET_KEY = "not-a-secret-this-is-the-library-test-suite"
DEBUG = True
ALLOWED_HOSTS = ["*"]
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "drf_spectacular",
    "apiver",
    "tests.testapp",
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "apiver mount fixture",
    "DESCRIPTION": "",
    "VERSION": "0.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# No ROOT_URLCONF — `apiver mount` never boots the project's urlconf, only
# reads/writes the aggregation root file directly.

APIVER_ROOT_DIR = "tests.fixtures_mount.api"
APIVER_ROOT_PREFIX = "api/"
# Named to prove `apiver alias` refuses a `--from` naming another alias
# (ticket #53) — never imported, so it needs no backing object.
APIVER_ALIASES = ["already_alias"]
