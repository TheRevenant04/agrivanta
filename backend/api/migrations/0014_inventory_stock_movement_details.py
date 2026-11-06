import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


def backfill_movement_dates(apps, schema_editor):
    StockMovement = apps.get_model("api", "StockMovement")
    for movement in StockMovement.objects.filter(date__isnull=True).iterator():
        movement.date = movement.created_at.date()
        movement.save(update_fields=["date"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0013_activity_assignees_farm_members"),
    ]

    operations = [
        migrations.AddField(
            model_name="stockmovement",
            name="activity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="stock_movements",
                to="api.activity",
            ),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="expense",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="stock_movements",
                to="api.expense",
            ),
        ),
        migrations.AddField(
            model_name="stockmovement",
            name="unit_cost",
            field=models.DecimalField(
                blank=True, decimal_places=4, max_digits=14, null=True
            ),
        ),
        migrations.AlterField(
            model_name="inventoryitem",
            name="reorder_level",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                default=None,
                max_digits=14,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="item",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="movements",
                to="api.inventoryitem",
            ),
        ),
        migrations.RunPython(backfill_movement_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stockmovement",
            name="date",
            field=models.DateField(),
        ),
        migrations.AddConstraint(
            model_name="inventoryitem",
            constraint=models.CheckConstraint(
                condition=Q(reorder_level__isnull=True)
                | Q(reorder_level__gte=0),
                name="inventory_reorder_level_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(
                condition=Q(type__in=["purchase", "usage", "adjustment"]),
                name="stock_movement_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(
                condition=(
                    Q(type__in=("purchase", "usage"), quantity__gt=0)
                    | (
                        Q(type="adjustment")
                        & ~Q(quantity=0)
                    )
                ),
                name="stock_movement_quantity_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(
                condition=Q(unit_cost__isnull=True) | Q(unit_cost__gte=0),
                name="stock_movement_unit_cost_nonnegative",
            ),
        ),
    ]
