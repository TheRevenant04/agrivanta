"""Database-level immutability for posted expenses and payments.

Triggers reject updates and deletes of posted expenses, reversal records and
payments, even when Django's model and queryset guards are bypassed (raw SQL,
bulk writes, cascades). The only permitted write to a posted original is
stamping ``reversed_at`` once, and only after its linked reversal row exists.
Reversal rows may only be inserted as an exact negative copy of an unreversed
original.

Django rebuilds a SQLite table when a later migration alters one of its
columns, which drops these triggers; such migrations must recreate them.
"""

from django.db import migrations

MESSAGE = "Posted transactions and reversals are immutable."
INSERT_MESSAGE = "Reversal must exactly offset an unreversed original."

EXPENSE_COLUMNS = (
    "id", "created_at", "updated_at", "farm_id", "cycle_id", "category",
    "amount", "date", "category_record_id", "supplier", "supplier_record_id",
    "attachment_reference", "status", "notes", "reversal_of_id",
)
PAYMENT_COLUMNS = (
    "id", "created_at", "updated_at", "farm_id", "type", "amount", "date",
    "linked_expense_id", "linked_sale_id", "reference", "reversal_of_id",
)
EXPENSE_OFFSET_COLUMNS = ("farm_id", "date", "category")
PAYMENT_OFFSET_COLUMNS = ("farm_id", "date", "type")


def _same(vendor, columns):
    if vendor == "postgresql":
        return " AND ".join(
            f"OLD.{c} IS NOT DISTINCT FROM NEW.{c}" for c in columns
        )
    return " AND ".join(f"OLD.{c} IS NEW.{c}" for c in columns)


def _match(vendor, left, right, column):
    if vendor == "postgresql":
        return f"{left}.{column} IS NOT DISTINCT FROM {right}.{column}"
    return f"{left}.{column} IS {right}.{column}"


def _conditions(vendor, table, columns, offset_columns, extra_links, locked):
    mark_allowed = (
        "OLD.reversal_of_id IS NULL AND OLD.reversed_at IS NULL "
        "AND NEW.reversed_at IS NOT NULL AND "
        + _same(vendor, columns)
        + f" AND EXISTS (SELECT 1 FROM {table} r WHERE r.reversal_of_id = OLD.id)"
    )
    if vendor == "postgresql":
        link_changed = "NEW.reversal_of_id IS DISTINCT FROM OLD.reversal_of_id"
    else:
        link_changed = "NEW.reversal_of_id IS NOT OLD.reversal_of_id"
    update = f"({link_changed})"
    update_condition = (
        f"{update} OR ({locked}) AND NOT ({mark_allowed})"
    )
    offsets = " AND ".join(
        [_match(vendor, "o", "NEW", c) for c in offset_columns + extra_links]
    )
    insert_condition = (
        "NEW.reversed_at IS NOT NULL OR (NEW.reversal_of_id IS NOT NULL "
        f"AND NOT EXISTS (SELECT 1 FROM {table} o "
        "WHERE o.id = NEW.reversal_of_id AND o.reversal_of_id IS NULL "
        "AND o.reversed_at IS NULL AND o.amount = -NEW.amount AND "
        + offsets
        + ("" if table == "api_payment" else " AND o.status = 'posted'")
        + "))"
    )
    return update_condition, insert_condition


def _spec(vendor):
    expense_update, expense_insert = _conditions(
        vendor,
        "api_expense",
        EXPENSE_COLUMNS,
        EXPENSE_OFFSET_COLUMNS,
        ("cycle_id",),
        "OLD.status = 'posted' OR OLD.reversal_of_id IS NOT NULL",
    )
    expense_update = (
        "(OLD.status = 'draft' AND NEW.reversed_at IS NOT NULL) OR "
        + expense_update
    )
    payment_update, payment_insert = _conditions(
        vendor,
        "api_payment",
        PAYMENT_COLUMNS,
        PAYMENT_OFFSET_COLUMNS,
        ("linked_expense_id", "linked_sale_id"),
        "TRUE" if vendor == "postgresql" else "1",
    )
    return {
        "api_expense": {
            "update": expense_update,
            "delete": "OLD.status = 'posted' OR OLD.reversal_of_id IS NOT NULL",
            "insert": expense_insert,
        },
        "api_payment": {
            "update": payment_update,
            "delete": "TRUE" if vendor == "postgresql" else "1",
            "insert": payment_insert,
        },
    }


def _events(table):
    return (
        ("update", "UPDATE", MESSAGE),
        ("delete", "DELETE", MESSAGE),
        ("insert", "INSERT", INSERT_MESSAGE),
    )


def _create_sql(vendor):
    statements = []
    for table, conditions in _spec(vendor).items():
        for name, event, message in _events(table):
            trigger = f"{table}_immutable_{name}"
            condition = conditions[name]
            if vendor == "postgresql":
                row = "OLD" if event == "DELETE" else "NEW"
                statements.append(
                    f"CREATE FUNCTION {trigger}() RETURNS trigger AS $$ "
                    f"BEGIN IF {condition} THEN "
                    f"RAISE EXCEPTION '{message}' "
                    "USING ERRCODE = 'integrity_constraint_violation'; "
                    f"END IF; RETURN {row}; END; $$ LANGUAGE plpgsql"
                )
                statements.append(
                    f"CREATE TRIGGER {trigger} BEFORE {event} ON {table} "
                    f"FOR EACH ROW EXECUTE FUNCTION {trigger}()"
                )
            else:
                statements.append(
                    f"CREATE TRIGGER {trigger} BEFORE {event} ON {table} "
                    f"FOR EACH ROW WHEN {condition} "
                    f"BEGIN SELECT RAISE(ABORT, '{message}'); END"
                )
    return statements


def _drop_sql(vendor):
    statements = []
    for table in ("api_expense", "api_payment"):
        for name, _event, _message in _events(table):
            trigger = f"{table}_immutable_{name}"
            if vendor == "postgresql":
                statements.append(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
                statements.append(f"DROP FUNCTION IF EXISTS {trigger}()")
            else:
                statements.append(f"DROP TRIGGER IF EXISTS {trigger}")
    return statements


def create_triggers(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in ("sqlite", "postgresql"):
        return
    for statement in _create_sql(vendor):
        schema_editor.execute(statement)


def drop_triggers(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in ("sqlite", "postgresql"):
        return
    for statement in _drop_sql(vendor):
        schema_editor.execute(statement)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0018_posted_transaction_immutability"),
    ]

    operations = [migrations.RunPython(create_triggers, drop_triggers)]
