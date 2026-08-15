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
    "TITLE": "apiver test app",
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

# Required for SpectacularSwaggerView/docs_view() to actually render (ticket
# 22) — without it, drf-spectacular's bundled swagger_ui.html template is
# never discoverable and any real HTTP GET against a docs route 500s.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

ROOT_URLCONF = "tests.testapp.urls"

# Matches testapp/urls.py's own "api/v1/", "api/v2/", ... mounts (ADR 0007
# item 3) — set here, not per-test, so build_manifest()'s unregistered-route
# audit (ticket #106) has somewhere to resolve a Version's mount prefix from
# even in tests that only override APIVER_ROOT_DIR/APIVER_VERSIONS.
APIVER_ROOT_PREFIX = "api/"
