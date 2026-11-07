import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

from api.attachment_uploads import AttachmentASGIBodyLimit

application = AttachmentASGIBodyLimit(application)
