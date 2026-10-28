from django.apps import AppConfig


class TrainerConfig(AppConfig):
    name = "cs_map_trainer.web"
    label = "trainer"

    def ready(self):
        from . import signals  # noqa: F401
