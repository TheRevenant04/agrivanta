import pytest

from api.models import Customer, Farm, Supplier, User


RESOURCES = (
    ("/api/suppliers", Supplier, "supplier"),
    ("/api/customers", Customer, "customer"),
)

OPTIONAL_FIELDS = {
    "contactName": "Morgan Contact",
    "email": "morgan@example.test",
    "phone": "+1 555 0100",
    "address": "12 Farm Road",
    "notes": "Preferred contact by email.",
}


@pytest.mark.parametrize(("path", "model", "noun"), RESOURCES)
def test_counterparties_support_crud_with_optional_fields(
    client, path, model, noun
):
    created = client.post(
        path, {"name": "  Meadow Supply  "}, format="json"
    )
    assert created.status_code == 201
    profile = created.data
    assert profile["name"] == "Meadow Supply"
    assert {
        key: profile[key]
        for key in ("contactName", "email", "phone", "address", "notes")
    } == {
        "contactName": "",
        "email": "",
        "phone": "",
        "address": "",
        "notes": "",
    }

    assert profile in client.get(path).data
    assert client.get(f"{path}/{profile['id']}").data == profile

    updated = client.put(
        f"{path}/{profile['id']}", OPTIONAL_FIELDS, format="json"
    )
    assert updated.status_code == 200
    assert updated.data["name"] == profile["name"]
    assert {
        key: updated.data[key] for key in OPTIONAL_FIELDS
    } == OPTIONAL_FIELDS
    assert client.get(f"{path}/{profile['id']}").data == updated.data

    patched = client.patch(
        f"{path}/{profile['id']}",
        {"notes": "Updated note"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.data["notes"] == "Updated note"
    assert patched.data["email"] == OPTIONAL_FIELDS["email"]

    assert client.delete(f"{path}/{profile['id']}").status_code == 204
    assert client.get(f"{path}/{profile['id']}").status_code == 404
    assert not model.objects.filter(pk=profile["id"]).exists()


@pytest.mark.parametrize(("path", "_model", "_noun"), RESOURCES)
@pytest.mark.parametrize("name", [None, "", " \t "])
def test_counterparties_reject_missing_or_blank_names(
    client, path, _model, _noun, name
):
    response = client.post(path, {"name": name}, format="json")

    assert response.status_code == 400
    assert response.data["field"] == "name"
    assert "name is required" in response.data["detail"].lower()


@pytest.mark.parametrize(("path", "_model", "_noun"), RESOURCES)
def test_counterparties_allow_duplicate_names(client, path, _model, _noun):
    first = client.post(path, {"name": "Same Name"}, format="json")
    second = client.post(path, {"name": "Same Name"}, format="json")

    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]
    matching = [
        row
        for row in client.get(path).data
        if row["name"] == "Same Name"
    ]
    assert {row["id"] for row in matching} == {
        first.data["id"],
        second.data["id"],
    }


def test_supplier_and_customer_empty_lists(client):
    assert client.get("/api/suppliers").data == []
    farm_id = client.get("/api/farm").data["id"]
    Customer.objects.filter(farm_id=farm_id).delete()
    assert client.get("/api/customers").data == []


@pytest.mark.parametrize(("path", "_model", "_noun"), RESOURCES)
def test_counterparty_email_must_be_valid(client, path, _model, _noun):
    response = client.post(
        path,
        {"name": "Email Check", "email": "not-an-email"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["field"] == "email"


@pytest.mark.parametrize(("path", "_model", "_noun"), RESOURCES)
def test_counterparty_endpoints_require_authentication(
    anon, path, _model, _noun
):
    detail = f"{path}/00000000-0000-0000-0000-000000000000"
    requests = (
        ("get", path, None),
        ("post", path, {"name": "Unauthorized"}),
        ("get", detail, None),
        ("put", detail, {"name": "Unauthorized"}),
        ("patch", detail, {"notes": "Unauthorized"}),
        ("delete", detail, None),
    )

    for method, url, payload in requests:
        response = getattr(anon, method)(
            url, payload, format="json"
        ) if payload is not None else getattr(anon, method)(url)
        assert response.status_code == 401, (method, url, response.data)


@pytest.mark.parametrize(("path", "model", "noun"), RESOURCES)
def test_counterparty_records_are_isolated_to_active_farm(
    client, path, model, noun
):
    foreign_user = User.objects.create_user(
        email="other-farm@agrivanta.test", password="password123"
    )
    foreign_farm = Farm.objects.create(
        owner=foreign_user, name="Other Farm", reporting_currency="USD"
    )
    foreign_profile = model.objects.create(
        farm=foreign_farm, name="Private Profile"
    )

    own_profiles = client.get(path).data
    assert all(row["id"] != str(foreign_profile.id) for row in own_profiles)
    url = f"{path}/{foreign_profile.id}"
    assert client.get(url).status_code == 404
    assert (
        client.put(url, {"contactName": "Changed"}, format="json").status_code
        == 404
    )
    assert (
        client.patch(url, {"notes": "Changed"}, format="json").status_code
        == 404
    )
    assert client.delete(url).status_code == 404
    foreign_profile.refresh_from_db()
    assert foreign_profile.name == "Private Profile"
    assert foreign_profile.contact_name == ""
