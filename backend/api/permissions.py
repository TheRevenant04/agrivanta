from collections.abc import Collection

from rest_framework.permissions import BasePermission, IsAuthenticated

from .models import Role


class RolePermission(BasePermission):
    """Allow authenticated users whose farm role is listed on the view."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        role = getattr(user, "role", None)
        if role not in Role.values:
            return False

        allowed_roles = getattr(view, "allowed_roles", ())
        if isinstance(allowed_roles, str) or not isinstance(
            allowed_roles, Collection
        ):
            return False

        return role in allowed_roles


class RolePermissionMixin:
    """Configure a view's allowed farm roles with its ``allowed_roles``."""

    allowed_roles: Collection[str] = ()
    permission_classes = (IsAuthenticated, RolePermission)
