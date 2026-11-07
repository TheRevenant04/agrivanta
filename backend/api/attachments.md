# Transaction attachments

Authenticated farm users can use `GET` and multipart `POST` (field `file`) at
`/api/expenses/{id}/attachments` and `/api/payments/{id}/attachments`. `GET`
and `DELETE` on `/{attachment_id}` download and remove an attachment.
Downloads are private, non-cacheable attachments. Responses contain metadata,
not storage paths or URLs. Uploads are limited to 10 MiB and PDF, JPEG, or PNG.
Duplicate content on the same transaction is rejected. Attachments may be
added to recorded transactions, but cannot be removed from posted expenses or
recorded payments. Deleting a draft expense also removes its files after commit.
Multipart parsing stops when the total file content exceeds 10 MiB. Under the
provided ASGI application, the entire request is additionally limited to 10 MiB
plus 64 KiB of multipart overhead before Django buffers it. Servers or proxies
that buffer requests before the application need their own request limits.

The `attachments` Django storage alias defaults to a private local directory
outside the static and media roots. To use an S3-compatible Django storage
backend, configure this alias in Django settings and ensure its bucket and
objects are private; no particular backend SDK is required by the application.
Do not expose either the private directory or the legacy `MEDIA_ROOT` through
a web server. The development media URL route is deliberately disabled.
Pre-existing attachment records continue to read their original storage; they
are served only through the authenticated download endpoint. Legacy content is
checked for duplicates when a file is uploaded to the same transaction.
