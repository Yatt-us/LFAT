"""Storage for records which must never be served from MEDIA_URL."""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url='/fichiers-prives-inaccessibles/')

    def url(self, name):
        # A file name is not an authorization token. Use the object-specific views.
        return '/fichiers-prives-inaccessibles/'


private_media_storage = PrivateMediaStorage()
