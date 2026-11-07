import re

from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from django.core.handlers.asgi import get_script_prefix

MAX_SIZE = 10 * 1024 * 1024
# Allow multipart headers and non-file fields while bounding ASGI body spooling.
MAX_REQUEST_SIZE = MAX_SIZE + 64 * 1024
ATTACHMENT_PATH = re.compile(r"^/api/(?:expenses|payments)/[^/]+/attachments$")


class AttachmentSizeLimitHandler(FileUploadHandler):
    """Reject the request before any oversized chunk reaches storage handlers."""

    def __init__(self, request):
        super().__init__(request)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > MAX_SIZE:
            self.request.attachment_upload_too_large = True
            raise StopUpload(connection_reset=True)
        return raw_data

    def file_complete(self, file_size):
        return None


class AttachmentASGIBodyLimit:
    """Bound Django's ASGI body spool before its multipart parser runs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "").removeprefix(get_script_prefix(scope))
        if not (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and ATTACHMENT_PATH.fullmatch(path)
        ):
            return await self.app(scope, receive, send)

        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_SIZE:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited_receive, send)
        if too_large:
            body = b'{"detail":"Attachment request exceeds the upload limit.","field":"file"}'
            await send({
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
