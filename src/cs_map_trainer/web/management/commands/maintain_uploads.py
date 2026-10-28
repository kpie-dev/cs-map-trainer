import time

from django.core.management.base import BaseCommand

from cs_map_trainer.web.tasks import maintain


class Command(BaseCommand):
    help = "Clean expired inputs and recover queued dispatches; never retry parsing."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **options):
        while True:
            maintain()
            if not options["loop"]:
                return
            time.sleep(60)
