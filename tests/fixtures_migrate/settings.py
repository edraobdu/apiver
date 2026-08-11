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
    "TITLE": "apiver migrate fixture",
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

ROOT_URLCONF = "tests.fixtures_migrate.urls"

# The parent package (tests/fixtures_migrate/api/) is committed; the leaf
# (api/v1/, and api/urls.py) is what `apiver migrate` writes, and tests
# clean it up after themselves so the fixture tree stays pristine between
# runs.
APIVER_BASE_VERSION = "v1"
APIVER_ROOT_DIR = "tests.fixtures_migrate.api"
APIVER_ROOT_PREFIX = "api/"
APIVER_VERSIONS = ["v1"]
