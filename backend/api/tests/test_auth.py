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

    assert response.status_code == 409
    assert response.data["field"] == "email"


def test_register_requires_email_and_password(db, anon):
    missing_email = register(anon, email="")
    missing_password = register(anon, password="")

    assert missing_email.status_code == 400
    assert missing_email.data["field"] == "email"
    assert missing_password.status_code == 400
    assert missing_password.data["field"] == "password"


def test_login_me_logout_flow(db, anon, session):
    login = anon.post(
        "/api/auth/login",
        {
            "email": "OWNER@agrivanta.test",
            "password": "password123",
        },
        format="json",
    )
    assert login.status_code == 200
    assert login.data["user"]["id"] == session["user"]["id"]

    me = session["client"].get("/api/auth/me")
    assert me.status_code == 200
    assert me.data["email"] == "owner@agrivanta.test"

    logout = session["client"].post("/api/auth/logout")
    assert logout.status_code == 204

    after_logout = session["client"].get("/api/auth/me")
    assert after_logout.status_code == 401


def test_login_rejects_bad_credentials(db, anon, session):
    response = anon.post(
        "/api/auth/login",
        {"email": "owner@agrivanta.test", "password": "wrong"},
        format="json",
    )
    assert response.status_code == 401


def test_unauthenticated_requests_are_rejected(db, anon):
    assert anon.get("/api/farm").status_code == 401


def test_registration_bootstraps_one_farm_per_user(db, anon):
    register(anon)
    register(anon, email="second@agrivanta.test")

    assert User.objects.count() == 2
    assert Farm.objects.count() == 2
    assert ActivityType.objects.filter(standard=True).count() == 10
    assert Customer.objects.count() == 4
