from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "starting_migration",
    [
        "0016_worker_labourrecord",
        "0018_customer_address_customer_contact_name_and_more",
        "0018_recurring_expense_reminders",
    ],
)
def test_upgrade_preserves_existing_data(starting_migration):
    try:
        MigrationExecutor(connection).migrate([("api", "0016_worker_labourrecord")])
        executor = MigrationExecutor(connection)
        executor.migrate([("api", starting_migration)])
        apps = executor.loader.project_state([("api", starting_migration)]).apps

        user = apps.get_model("api", "User").objects.create(email="migration@example.com")
        farm = apps.get_model("api", "Farm").objects.create(
            owner=user, name="Existing farm", reporting_currency="USD"
        )
        worker = apps.get_model("api", "Worker").objects.create(farm=farm, name="Worker")
        field = apps.get_model("api", "Field").objects.create(
            farm=farm, name="Field", area=Decimal("1")
        )
        crop = apps.get_model("api", "Crop").objects.create(farm=farm, name="Crop")
        cycle = apps.get_model("api", "CropCycle").objects.create(
            farm=farm, field=field, crop=crop, start_date=date(2026, 1, 1)
        )
        activity_type = apps.get_model("api", "ActivityType").objects.create(
            farm=farm, name="Activity type", category="other"
        )
        activity = apps.get_model("api", "Activity").objects.create(
            farm=farm, cycle=cycle, type=activity_type, planned_date=date(2026, 1, 2)
        )
        labour = apps.get_model("api", "LabourRecord").objects.create(
            farm=farm, worker=worker, activity=activity, hours=Decimal("2"),
            hourly_cost=Decimal("15"), date=date(2026, 1, 2),
        )
        supplier_fields = {"farm": farm, "name": "Supplier"}
        if starting_migration == "0018_customer_address_customer_contact_name_and_more":
            supplier_fields["notes"] = "Existing notes"
        supplier = apps.get_model("api", "Supplier").objects.create(**supplier_fields)

        if starting_migration == "0018_recurring_expense_reminders":
            category = apps.get_model("api", "ExpenseCategoryRecord").objects.create(
                farm=farm, name="Existing category"
            )
            template = apps.get_model("api", "RecurringExpenseTemplate").objects.create(
                farm=farm,
                category=category,
                amount=Decimal("10.0000"),
                frequency="monthly",
                next_due_date=date(2026, 12, 1),
            )

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        executor = MigrationExecutor(connection)
        assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
        apps = executor.loader.project_state().apps
        assert apps.get_model("api", "Worker").objects.get(pk=worker.pk).name == "Worker"
        saved_labour = apps.get_model("api", "LabourRecord").objects.get(pk=labour.pk)
        assert saved_labour.worker_id == worker.pk
        assert saved_labour.activity_id == activity.pk
        assert saved_labour.hours == Decimal("2.0000")
        assert saved_labour.hourly_cost == Decimal("15.0000")
        saved_supplier = apps.get_model("api", "Supplier").objects.get(pk=supplier.pk)
        assert saved_supplier.name == "Supplier"
        if starting_migration == "0018_customer_address_customer_contact_name_and_more":
            assert saved_supplier.notes == "Existing notes"
        if starting_migration == "0018_recurring_expense_reminders":
            saved = apps.get_model("api", "RecurringExpenseTemplate").objects.get(pk=template.pk)
            assert saved.amount == Decimal("10.0000")
            assert saved.category_id == category.pk
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
