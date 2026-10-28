import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cs_map_trainer.web.settings")
application = get_wsgi_application()
