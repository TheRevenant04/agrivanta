from django.db import IntegrityError, transaction
import pytest

from api.models import Role, User


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("role", Role.values)
def test_user_can_be_created_and_looked_up_by_email_with_each_role(role):
    email = f"{role}@agrivanta.test"

    created = User.objects.create_user(email=email, password="password123", role=role)

    assert created.role == role
    assert User.objects.get(email=email) == created


def test_duplicate_user_email_is_rejected():
    User.objects.create_user(email="owner@agrivanta.test", password="password123")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            email="owner@agrivanta.test", password="password123"
        )


def test_invalid_user_role_is_rejected_by_database_constraint():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(
            email="invalid-role@agrivanta.test",
            password="password123",
            role="admin",
        )


def test_user_without_role_defaults_to_owner():
    user = User.objects.create_user(
        email="default-role@agrivanta.test", password="password123"
    )

    assert user.role == Role.OWNER
