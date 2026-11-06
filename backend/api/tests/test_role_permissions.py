from types import SimpleNamespace

import pytest
from django.urls import path
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView

from api.models import Role, User
from api.permissions import RolePermissionMixin


pytestmark = [
    pytest.mark.django_db,
    pytest.mark.urls(__name__),
]


class ProtectedView(RolePermissionMixin, APIView):
    allowed_roles = ()

    def get(self, request):
        return Response({"view_executed": True})


class OwnerView(ProtectedView):
    allowed_roles = (Role.OWNER,)


class ManagerView(ProtectedView):
    allowed_roles = (Role.MANAGER,)


class WorkerView(ProtectedView):
    allowed_roles = (Role.WORKER,)


class OwnerAndManagerView(ProtectedView):
    allowed_roles = (Role.OWNER, Role.MANAGER)


urlpatterns = [
    path("", ProtectedView.as_view()),
    path("owner/", OwnerView.as_view()),
    path("manager/", ManagerView.as_view()),
    path("worker/", WorkerView.as_view()),
    path("owner-manager/", OwnerAndManagerView.as_view()),
]


@pytest.mark.parametrize(
    ("url", "allowed_role"),
    [
        ("/owner/", Role.OWNER),
        ("/manager/", Role.MANAGER),
        ("/worker/", Role.WORKER),
    ],
)
@pytest.mark.parametrize("role", Role.values)
def test_single_role_views_allow_only_the_configured_role(url, allowed_role, role):
    user = User(email=f"{role}@agrivanta.test", role=role)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(url)

    if role == allowed_role:
        assert response.status_code == 200
        assert response.data == {"view_executed": True}
    else:
        assert response.status_code == 403


@pytest.mark.parametrize("role", Role.values)
def test_empty_allowed_roles_deny_every_authenticated_role(role):
    user = User(email=f"{role}@agrivanta.test", role=role)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/")

    assert response.status_code == 403


def test_unauthenticated_request_is_rejected_before_view_execution():
    response = APIClient().get("/owner/")

    assert response.status_code in (401, 403)
    assert response.data != {"view_executed": True}


@pytest.mark.parametrize(
    "user",
    [
        pytest.param(SimpleNamespace(is_authenticated=True), id="missing-role"),
        pytest.param(
            SimpleNamespace(is_authenticated=True, role="admin"),
            id="unsupported-role",
        ),
    ],
)
def test_missing_or_unsupported_role_is_denied_without_server_error(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/owner/")

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("url", "allowed_roles"),
    [
        ("/owner-manager/", {Role.OWNER, Role.MANAGER}),
        ("/owner/", {Role.OWNER}),
    ],
)
@pytest.mark.parametrize("role", Role.values)
def test_mixin_is_reusable_with_independent_view_configurations(
    url, allowed_roles, role
):
    user = User(email=f"{role}@agrivanta.test", role=role)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get(url)

    if role in allowed_roles:
        assert response.status_code == 200
    else:
        assert response.status_code == 403
