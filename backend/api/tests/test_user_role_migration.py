import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_role_constraint_migration_normalizes_legacy_roles():
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([("api", "0007_notification")])
        old_apps = executor.loader.project_state(
            [("api", "0007_notification")]
        ).apps
        OldUser = old_apps.get_model("api", "User")

        for role in ("owner", "manager", "worker"):
            OldUser.objects.create(
                email=f"{role}@migration.test", password="unused", role=role
            )
        OldUser.objects.create(
            email="invalid@migration.test", password="unused", role="admin"
        )
        OldUser.objects.create(
            email="empty@migration.test", password="unused", role=""
        )
        OldUser.objects.create(email="default@migration.test", password="unused")

        MigrationExecutor(connection).migrate([("api", "0008_enforce_user_role")])
        new_apps = MigrationExecutor(connection).loader.project_state(
            [("api", "0008_enforce_user_role")]
        ).apps
        NewUser = new_apps.get_model("api", "User")

        assert NewUser.objects.get(email="owner@migration.test").role == "owner"
        assert NewUser.objects.get(email="manager@migration.test").role == "manager"
        assert NewUser.objects.get(email="worker@migration.test").role == "worker"
        assert NewUser.objects.get(email="invalid@migration.test").role == "worker"
        assert NewUser.objects.get(email="empty@migration.test").role == "worker"
        assert NewUser.objects.get(email="default@migration.test").role == "owner"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
