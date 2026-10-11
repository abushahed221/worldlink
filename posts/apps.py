from django.apps import AppConfig


class PostsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "posts"

    def ready(self):
        import posts.signals  # noqa
        import posts.signals_notifications  # noqa
        import posts.signals_admin  # noqa
        import posts.signals_security  # noqa