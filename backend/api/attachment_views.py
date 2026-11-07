import hashlib
import os
import uuid

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.utils.text import get_valid_filename
from rest_framework import status
from rest_framework.response import Response

from .exceptions import ApiError
from .attachment_uploads import AttachmentSizeLimitHandler, MAX_SIZE
from .models import Attachment, Expense, ExpenseStatus, Payment
from .serializers import serialize_attachment
from .views import APIView, get_farm, scoped_get

TYPES = {
    "application/pdf": (".pdf",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
}


def validate_upload(upload):
    if upload is None:
        raise ApiError("A file is required.", field="file")
    digest = hashlib.sha256()
    size = 0
    header = b""
    tail = b""
    for chunk in upload.chunks():
        size += len(chunk)
        if size > MAX_SIZE:
            raise ApiError("File must not exceed 10 MiB.", field="file")
        header = (header + chunk)[:16]
        tail = (tail + chunk)[-1024:]
        digest.update(chunk)
    if not size:
        raise ApiError("File must not be empty.", field="file")
    if header.startswith((b"%PDF-1.", b"%PDF-2.")) and tail.rstrip().endswith(b"%%EOF"):
        content_type = "application/pdf"
    elif header.startswith(b"\xff\xd8\xff") and tail.endswith(b"\xff\xd9"):
        content_type = "image/jpeg"
    elif (
        header.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        and tail.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    ):
        content_type = "image/png"
    else:
        raise ApiError("File must be a PDF, JPEG, or PNG.", field="file")
    name = str(upload.name).replace("\\", "/").rsplit("/", 1)[-1]
    ext = os.path.splitext(name)[1].lower()
    supplied_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
    if (ext and ext not in TYPES[content_type]) or (
        supplied_type not in ("", "application/octet-stream", content_type)
    ):
        raise ApiError("File type conflicts with its content.", field="file")
    name = get_valid_filename(name)[:255] or f"attachment{TYPES[content_type][0]}"
    upload.seek(0)
    return name, content_type, size, digest.hexdigest()


def parent_for(request, kind, parent_id, lock=False):
    model = Expense if kind == "expenses" else Payment
    farm = get_farm(request.user)
    if not lock:
        return scoped_get(model, farm, parent_id, "Not found.")
    try:
        return model.objects.select_for_update().get(farm=farm, pk=parent_id)
    except (model.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ApiError("Not found.", status.HTTP_404_NOT_FOUND)


def find_attachment(parent, attachment_id):
    try:
        return parent.attachments.get(pk=attachment_id)
    except (Attachment.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ApiError("Not found.", status.HTTP_404_NOT_FOUND)


class AttachmentListView(APIView):
    def initialize_request(self, request, *args, **kwargs):
        if request.method == "POST":
            request.upload_handlers.insert(0, AttachmentSizeLimitHandler(request))
        return super().initialize_request(request, *args, **kwargs)

    def get(self, request, kind, parent_id):
        parent = parent_for(request, kind, parent_id)
        return Response([serialize_attachment(a) for a in parent.attachments.all()])

    def post(self, request, kind, parent_id):
        # Check the farm before reading or storing the uploaded content.
        parent_for(request, kind, parent_id)
        upload = request.FILES.get("file")
        if getattr(request._request, "attachment_upload_too_large", False):
            raise ApiError("File must not exceed 10 MiB.", field="file")
        name, content_type, size, digest = validate_upload(upload)
        upload = request.FILES["file"]
        stored = None
        try:
            with transaction.atomic():
                parent = parent_for(request, kind, parent_id, lock=True)
                if parent.attachments.filter(sha256=digest).exists():
                    raise ApiError("Duplicate attachment content.", field="file")
                # Legacy records predate digests; compare them without exposing paths.
                for legacy in parent.attachments.filter(sha256__isnull=True):
                    if legacy.file:
                        with legacy.file.open("rb") as source:
                            old_hash = hashlib.file_digest(source, "sha256").hexdigest()
                        if old_hash == digest:
                            raise ApiError("Duplicate attachment content.", field="file")
                attachment = Attachment(
                    **({"expense": parent} if kind == "expenses" else {"payment": parent}),
                    name=name, content_type=content_type, size=size, sha256=digest,
                )
                attachment.private_file.save(uuid.uuid4().hex, upload, save=False)
                stored = attachment.private_file
                attachment.save()
        except IntegrityError:
            if stored:
                stored.delete(save=False)
            raise ApiError("Duplicate attachment content.", field="file")
        except Exception:
            if stored:
                stored.delete(save=False)
            raise
        return Response(serialize_attachment(attachment), status=status.HTTP_201_CREATED)


class AttachmentDetailView(APIView):
    def get(self, request, kind, parent_id, attachment_id):
        parent = parent_for(request, kind, parent_id)
        attachment = find_attachment(parent, attachment_id)
        file = attachment.private_file or attachment.file
        try:
            stream = file.open("rb")
        except (FileNotFoundError, OSError):
            raise ApiError("Not found.", status.HTTP_404_NOT_FOUND)
        extension = TYPES.get(attachment.content_type, ("",))[0]
        response = FileResponse(
            stream, as_attachment=True, filename=f"attachment{extension}",
            content_type=attachment.content_type or "application/octet-stream",
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    def delete(self, request, kind, parent_id, attachment_id):
        with transaction.atomic():
            parent = parent_for(request, kind, parent_id, lock=True)
            attachment = find_attachment(parent, attachment_id)
            if isinstance(parent, Payment) or parent.status == ExpenseStatus.POSTED or parent.is_reversal:
                raise ApiError("Transaction is immutable.", status.HTTP_409_CONFLICT)
            attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
