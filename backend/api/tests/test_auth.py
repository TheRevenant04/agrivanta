from rest_framework.authtoken.models import Token

from api.models import ActivityType, Customer, Farm, User

from .conftest import register


def test_register_creates_owner_farm_and_session(db, anon):
    response = register(anon)

    assert response.status_code == 201
    assert response.data["token"]
    assert response.data["user"]["email"] == "owner@agrivanta.test"
    assert response.data["user"]["role"] == "owner"

    user = User.objects.get(email="owner@agrivanta.test")
    assert user.farm.name == "Olive Owner's Farm"
    assert user.farm.reporting_currency == "USD"
    assert user.farm.activity_types.filter(standard=True).count() == 5
    assert user.farm.customers.count() == 2


def test_register_rejects_duplicate_email(db, anon):
    register(anon)
    response = register(anon)

    assert response.status_code == 400
    assert response.data["field"] == "email"
    assert response.data["detail"]


def test_register_requires_email_and_password(db, anon):
    missing_email = register(anon, email="")
    missing_password = register(anon, password="")

    assert missing_email.status_code == 400
    assert missing_email.data["field"] == "email"
    assert missing_password.status_code == 400
    assert missing_password.data["field"] == "password"
    assert missing_email.data["detail"]
    assert missing_password.data["detail"]


def test_register_rejects_malformed_email(db, anon):
    response = register(anon, email="not-an-email")

    assert response.status_code == 400
    assert response.data["field"] == "email"
    assert response.data["detail"]


def test_register_rejects_password_that_fails_configured_validators(db, anon):
    response = register(anon, password="123")

    assert response.status_code == 400
    assert response.data["field"] == "password"
    assert response.data["detail"]


def test_login_me_logout_flow(db, anon, session):
    login = anon.post(
        "/api/auth/login",
        {
            "email": "OWNER@agrivanta.test",
            "password": "OliveHarvest#42",
        },
        format="json",
    )
    assert login.status_code == 200
    assert login.data["token"]
    assert login.data["user"]["id"] == session["user"]["id"]

    me = session["client"].get("/api/auth/me")
    assert me.status_code == 200
    assert me.data["email"] == "owner@agrivanta.test"
    assert me.data["role"] == "owner"

    logout = session["client"].post("/api/auth/logout")
    assert logout.status_code == 204

    after_logout = session["client"].get("/api/auth/me")
    assert after_logout.status_code == 401


def test_login_rejects_bad_credentials(db, anon, session):
    existing_tokens = Token.objects.count()

    for email, password in (
        ("owner@agrivanta.test", "wrong"),
        ("unknown@agrivanta.test", "OliveHarvest#42"),
    ):
        response = anon.post(
            "/api/auth/login",
            {"email": email, "password": password},
            format="json",
        )
        assert response.status_code == 401
        assert "token" not in response.data
        assert Token.objects.count() == existing_tokens


def test_unauthenticated_requests_are_rejected(db, anon):
    assert anon.get("/api/auth/me").status_code == 401
    for method in ("get", "put", "patch", "post", "delete"):
        caller = getattr(anon, method)
        response = (
            caller("/api/farm")
            if method in {"get", "delete"}
            else caller("/api/farm", {}, format="json")
        )
        assert response.status_code == 401
    for method in ("get", "post"):
        caller = getattr(anon, method)
        response = caller("/api/fields") if method == "get" else caller(
            "/api/fields", {}, format="json"
        )
        assert response.status_code == 401
    for method in ("get", "put", "patch", "delete"):
        caller = getattr(anon, method)
        url = "/api/fields/00000000-0000-0000-0000-000000000000"
        response = (
            caller(url)
            if method in {"get", "delete"}
            else caller(url, {}, format="json")
        )
        assert response.status_code == 401


def test_registration_bootstraps_one_farm_per_user(db, anon):
    register(anon)
    register(anon, email="second@agrivanta.test")

    assert User.objects.count() == 2
    assert Farm.objects.count() == 2
    assert ActivityType.objects.filter(standard=True).count() == 10
    assert Customer.objects.count() == 4
