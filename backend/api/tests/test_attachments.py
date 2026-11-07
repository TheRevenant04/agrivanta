import base64
import uuid

import pytest
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from api.models import Attachment

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+/l9sAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0\x00\x02\xff\xd9"


@pytest.fixture(autouse=True)
def private_storage(monkeypatch):
    storage = InMemoryStorage()
    monkeypatch.setattr(Attachment._meta.get_field("private_file"), "storage", storage)
    return storage


@pytest.fixture
def transactions(client):
    expense = client.post(
        "/api/expenses",
        {"category": "overhead", "amount": 90, "date": "2026-03-07"},
        format="json",
    )
    payment = client.post(
        "/api/payments",
        {"type": "paid", "amount": 90, "date": "2026-03-07"},
        format="json",
    )
    assert expense.status_code == payment.status_code == 201
    return expense.data["id"], payment.data["id"]


def upload(client, url, data=PDF, name="invoice.pdf", content_type="application/pdf"):
    return client.post(
        url, {"file": SimpleUploadedFile(name, data, content_type=content_type)},
        format="multipart",
    )


@pytest.mark.parametrize("kind,index", [("expenses", 0), ("payments", 1)])
def test_upload_list_download_duplicate_and_delete(
    client, transactions, private_storage, django_capture_on_commit_callbacks, kind, index
):
    url = f"/api/{kind}/{transactions[index]}/attachments"
    assert client.get(url).data == []
    created = upload(client, url)
    assert created.status_code == 201, created.data
    assert set(created.data) == {"id", "name", "contentType", "size", "createdAt"}
    assert created.data["size"] == len(PDF)
    assert client.get(url).data == [created.data]
    record = Attachment.objects.get(pk=created.data["id"])
    assert record.private_file.name != "invoice.pdf"
    assert "invoice" not in record.private_file.name
    assert private_storage.exists(record.private_file.name)
    duplicate = upload(client, url, name="other.pdf")
    assert duplicate.status_code == 400
    assert "duplicate" in duplicate.data["detail"].lower()
    assert Attachment.objects.count() == 1
    downloaded = client.get(f"{url}/{record.id}")
    assert downloaded.status_code == 200
    assert b"".join(downloaded.streaming_content) == PDF
    assert downloaded["Content-Disposition"] == 'attachment; filename="attachment.pdf"'
    assert downloaded["X-Content-Type-Options"] == "nosniff"
    assert downloaded["Cache-Control"] == "private, no-store"
    if kind == "payments":
        assert client.delete(f"{url}/{record.id}").status_code == 409
        assert private_storage.exists(record.private_file.name)
    else:
        key = record.private_file.name
        with django_capture_on_commit_callbacks(execute=True):
            assert client.delete(f"{url}/{record.id}").status_code == 204
        assert not Attachment.objects.exists()
        assert not private_storage.exists(key)


@pytest.mark.parametrize(
    "data,name,mime,expected",
    [
        (PDF, "receipt.pdf", "application/pdf", 201),
        (JPEG, "receipt.jpg", "image/jpeg", 201),
        (PNG, "receipt.png", "image/png", 201),
        (PDF, "receipt", "application/octet-stream", 201),
        (b"", "receipt.pdf", "application/pdf", 400),
        (b"not a pdf", "receipt.pdf", "application/pdf", 400),
        (b"%PDF-1.4 fake", "receipt.pdf", "application/pdf", 400),
        (PDF, "receipt.png", "application/pdf", 400),
        (PDF, "receipt.pdf", "image/png", 400),
        (PDF, "receipt.txt", "application/pdf", 400),
    ],
)
def test_type_validation(client, transactions, data, name, mime, expected):
    url = f"/api/expenses/{transactions[0]}/attachments"
    response = upload(client, url, data, name, mime)
    assert response.status_code == expected, response.data
    assert Attachment.objects.count() == (expected == 201)


@override_settings(FILE_UPLOAD_MAX_MEMORY_SIZE=11 * 1024 * 1024)
@pytest.mark.parametrize("size,expected", [(10 * 1024 * 1024, 201), (10 * 1024 * 1024 + 1, 400)])
def test_size_boundary(client, transactions, size, expected):
    data = b"%PDF-1.4\n" + b"x" * (size - 14) + b"%%EOF"
    assert len(data) == size
    response = upload(client, f"/api/expenses/{transactions[0]}/attachments", data)
    assert response.status_code == expected, response.data
    assert Attachment.objects.count() == (expected == 201)


def test_missing_inputs_and_not_found(client, transactions, private_storage):
    url = f"/api/expenses/{transactions[0]}/attachments"
    assert client.post(url, {}, format="multipart").status_code == 400
    for missing in (str(uuid.uuid4()), "invalid"):
        assert upload(client, f"/api/expenses/{missing}/attachments").status_code == 404
        assert client.get(f"/api/expenses/{missing}/attachments").status_code == 404
        assert client.get(f"{url}/{missing}").status_code == 404
        assert client.delete(f"{url}/{missing}").status_code == 404
    assert not Attachment.objects.exists()
    assert private_storage.listdir("")[1] == []


def test_posted_expense_preserves_attachment(client, transactions, private_storage):
    expense_id = transactions[0]
    url = f"/api/expenses/{expense_id}/attachments"
    created = upload(client, url)
    record = Attachment.objects.get(pk=created.data["id"])
    assert client.post(f"/api/expenses/{expense_id}/post").status_code == 200
    assert client.delete(f"{url}/{record.id}").status_code == 409
    assert Attachment.objects.filter(pk=record.id).exists()
    assert private_storage.exists(record.private_file.name)


@pytest.mark.parametrize("kind,index", [("expenses", 0), ("payments", 1)])
def test_cross_farm_and_unauthenticated(client, transactions, private_storage, kind, index):
    url = f"/api/{kind}/{transactions[index]}/attachments"
    created = upload(client, url)
    attachment_id = created.data["id"]
    record = Attachment.objects.get(pk=attachment_id)
    other = APIClient()
    registered = other.post(
        "/api/auth/register",
        {"name": "Other", "email": "other@example.test", "password": "OtherHarvest#42"},
        format="json",
    )
    other.credentials(HTTP_AUTHORIZATION=f"Bearer {registered.data['token']}")
    for actor, expected in ((APIClient(), 401), (other, 404)):
        assert actor.get(url).status_code == expected
        assert upload(actor, url).status_code == expected
        assert actor.get(f"{url}/{attachment_id}").status_code == expected
        assert actor.delete(f"{url}/{attachment_id}").status_code == expected
    assert Attachment.objects.count() == 1
    assert private_storage.exists(record.private_file.name)


def test_attachment_id_is_scoped_to_its_parent(client, transactions, private_storage):
    expense_url = f"/api/expenses/{transactions[0]}/attachments"
    payment_url = f"/api/payments/{transactions[1]}/attachments"
    created = upload(client, expense_url)
    record = Attachment.objects.get(pk=created.data["id"])
    assert client.get(f"{payment_url}/{record.pk}").status_code == 404
    assert client.delete(f"{payment_url}/{record.pk}").status_code == 404
    assert private_storage.exists(record.private_file.name)


def test_failed_record_creation_removes_uploaded_file(
    client, transactions, private_storage, monkeypatch
):
    def fail(*args, **kwargs):
        raise RuntimeError("database failure")

    monkeypatch.setattr(Attachment, "save", fail)
    with pytest.raises(RuntimeError, match="database failure"):
        upload(client, f"/api/expenses/{transactions[0]}/attachments")
    assert not Attachment.objects.exists()
    assert private_storage.listdir("attachments")[1] == []


def test_draft_parent_delete_cleans_file_after_commit(
    client, transactions, private_storage, django_capture_on_commit_callbacks
):
    url = f"/api/expenses/{transactions[0]}/attachments"
    record_id = upload(client, url).data["id"]
    record = Attachment.objects.get(pk=record_id)
    key = record.private_file.name
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(f"/api/expenses/{transactions[0]}").status_code == 204
    assert not Attachment.objects.filter(pk=record_id).exists()
    assert not private_storage.exists(key)


def test_legacy_attachment_stays_private_and_blocks_duplicate(
    client, transactions, monkeypatch
):
    legacy_storage = InMemoryStorage()
    monkeypatch.setattr(Attachment._meta.get_field("file"), "storage", legacy_storage)
    record = Attachment(expense_id=transactions[0], name="old.pdf")
    record.file.save("old.pdf", SimpleUploadedFile("old.pdf", PDF))
    url = f"/api/expenses/{transactions[0]}/attachments"
    response = client.get(url)
    assert response.status_code == 200
    assert "url" not in response.data[0]
    downloaded = client.get(f"{url}/{record.id}")
    assert b"".join(downloaded.streaming_content) == PDF
    assert downloaded["Content-Type"] == "application/octet-stream"
    assert client.get("/media/" + record.file.name).status_code == 404
    duplicate = upload(client, url)
    assert duplicate.status_code == 400
    assert "duplicate" in duplicate.data["detail"].lower()
    assert Attachment.objects.count() == 1
