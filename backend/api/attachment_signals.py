from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment


@receiver(post_delete, sender=Attachment)
def delete_attachment_files(sender, instance, using, **kwargs):
    for field in (instance.private_file, instance.file):
        if field:
            storage, name = field.storage, field.name
            transaction.on_commit(
                lambda storage=storage, name=name: storage.delete(name), using=using
            )
