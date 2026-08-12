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
    "TITLE": "apiver diff fixture",
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

# No ROOT_URLCONF — `apiver diff`/`apiver check` build each version's schema
# directly from its own registry.py, independent of the Aggregation Root
# (see schema_diff.get_schema's docstring), so this fixture never wires one.

APIVER_ROOT_DIR = "tests.fixtures_diff.api"
APIVER_ROOT_PREFIX = "api/"
APIVER_VERSIONS = ["v1", "v2"]
