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
    "TITLE": "apiver remove fixture",
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

APIVER_ROOT_DIR = "tests.fixtures_remove.api"
APIVER_ROOT_PREFIX = "api/"
APIVER_BASE_VERSION = "v1"
APIVER_VERSIONS = [
    "v1",
    "v2",
    "v10",
    "v11",
    "v12",
    "v20",
    "v21",
    "v30",
    "v31",
    "v40",
]
