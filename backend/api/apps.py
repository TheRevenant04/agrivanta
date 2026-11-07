from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        from . import attachment_signals  # noqa: F401
        from . import audit  # noqa: F401
