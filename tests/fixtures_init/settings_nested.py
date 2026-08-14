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
]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "apiver init nested-router fixture",
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

ROOT_URLCONF = "tests.fixtures_init.urls_nested"

# A separate generated root from tests.fixtures_init.settings' ("api"), so
# the two fixtures' generated output never collides.
APIVER_ROOT_DIR = "tests.fixtures_init.api_nested"
APIVER_ROOT_PREFIX = ""
APIVER_VERSIONS = ["v1"]
