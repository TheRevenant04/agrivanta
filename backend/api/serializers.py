from datetime import date
from decimal import Decimal, InvalidOperation


def as_id(value):
    return str(value)


def as_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def as_date(value):
    return value.isoformat() if value else None


def as_datetime(value):
    return value.isoformat() if value else None


def serialize_user(user):
    return {"id": as_id(user.id), "email": user.email, "role": user.role}


def serialize_farm(farm):
    return {
        "id": as_id(farm.id),
        "name": farm.name,
        "reportingCurrency": farm.reporting_currency,
    }


def serialize_season(season):
    payload = {
        "id": as_id(season.id),
        "farmId": as_id(season.farm_id),
        "name": season.name,
        "startDate": as_date(season.start_date),
        "endDate": as_date(season.end_date),
    }
    if season.year is not None:
        payload["year"] = season.year
    return payload


def serialize_reporting_period(period):
    payload = {
        "id": as_id(period.id),
        "farmId": as_id(period.farm_id),
        "name": period.name,
        "startDate": as_date(period.start_date),
        "endDate": as_date(period.end_date),
    }
    if period.year is not None:
        payload["year"] = period.year
    return payload


def serialize_field(field):
    payload = {
        "id": as_id(field.id),
        "farmId": as_id(field.farm_id),
        "name": field.name,
        "area": as_number(field.area),
    }
    if field.notes:
        payload["notes"] = field.notes
    if field.polygon is not None:
        payload["polygon"] = field.polygon
    return payload


def serialize_crop(crop):
    return {"id": as_id(crop.id), "name": crop.name}


def serialize_variety(variety):
    return {
        "id": as_id(variety.id),
        "cropId": as_id(variety.crop_id),
        "name": variety.name,
    }


def serialize_unit(unit):
    return {
        "id": as_id(unit.id),
        "name": unit.name,
        "baseMeasure": unit.base_measure,
    }


def serialize_conversion(conversion):
    return {
        "id": as_id(conversion.id),
        "fromUnitId": as_id(conversion.from_unit_id),
        "toUnitId": as_id(conversion.to_unit_id),
        "factor": as_number(conversion.factor),
    }


def serialize_cycle(cycle):
    payload = {
        "id": as_id(cycle.id),
        "fieldId": as_id(cycle.field_id),
        "cropId": as_id(cycle.crop_id),
        "varietyId": (
            as_id(cycle.variety_id) if cycle.variety_id else None
        ),
        "cycleType": cycle.cycle_type,
        "startDate": as_date(cycle.start_date),
        "status": cycle.status,
    }
    if cycle.end_date:
        payload["endDate"] = as_date(cycle.end_date)
    if cycle.expected_yield is not None:
        payload["expectedYield"] = as_number(cycle.expected_yield)
    if cycle.expected_price is not None:
        payload["expectedPrice"] = as_number(cycle.expected_price)
    return payload


def cycle_label(cycle):
    return (
        f"{cycle.field.name} \u2014 {cycle.crop.name} "
        f"{cycle.start_date.year}"
    )


def serialize_cycle_ref(cycle):
    return {"id": as_id(cycle.id), "label": cycle_label(cycle)}


def serialize_activity_type(activity_type):
    return {
        "id": as_id(activity_type.id),
        "name": activity_type.name,
        "category": activity_type.category,
        "standard": activity_type.standard,
        "inputs": [
            {
                "itemName": item["itemName"],
                "quantity": as_number(Decimal(str(item["quantity"]))),
            }
            for item in activity_type.default_inputs
        ],
        "labourHours": as_number(activity_type.default_labour_hours),
        "equipment": activity_type.default_equipment,
    }


def serialize_activity(activity):
    return {
        "id": as_id(activity.id),
        "cycleId": as_id(activity.cycle_id),
        "typeId": as_id(activity.type_id),
        "assignedWorkerIds": [
            as_id(user.id) for user in activity.assignees.all()
        ],
        "plannedDate": as_date(activity.planned_date),
        "status": activity.status,
        "description": activity.description or None,
        "resourceNeeds": {
            "inputs": [
                {
                    "id": as_id(need.id),
                    "itemName": need.item_name,
                    "quantity": as_number(need.quantity),
                }
                for need in activity.input_needs.all()
            ],
            "labourHours": as_number(activity.labour_hours),
            "equipment": activity.equipment or "",
        },
    }


def serialize_inventory_item(item):
    return {
        "id": as_id(item.id),
        "name": item.name,
        "unitId": as_id(item.unit_id),
        "reorderLevel": as_number(item.reorder_level),
        "currentQuantity": as_number(item.current_quantity()),
        "lowStock": item.is_low_stock(),
    }


def serialize_movement(movement):
    payload = {
        "id": as_id(movement.id),
        "itemId": as_id(movement.item_id),
        "type": movement.type,
        "quantity": as_number(movement.quantity),
        "date": as_date(movement.date),
        "unitCost": as_number(movement.unit_cost),
        "activityId": (
            as_id(movement.activity_id) if movement.activity_id else None
        ),
        "expenseId": (
            as_id(movement.expense_id) if movement.expense_id else None
        ),
    }
    if movement.note:
        payload["note"] = movement.note
    return payload


def serialize_attachment(attachment):
    payload = {"id": as_id(attachment.id), "name": attachment.name}
    if attachment.file:
        payload["url"] = attachment.file.url
    return payload


def serialize_expense(expense):
    return {
        "id": as_id(expense.id),
        "cycleId": (
            as_id(expense.cycle_id) if expense.cycle_id else None
        ),
        "category": expense.category,
        "amount": as_number(expense.amount),
        "date": as_date(expense.date),
        "supplier": expense.supplier or None,
        "status": expense.status,
        "attachments": [
            serialize_attachment(attachment)
            for attachment in expense.attachments.all()
        ],
        "notes": expense.notes or None,
    }


def serialize_budget(budget):
    return {
        "id": as_id(budget.id),
        "cycleId": as_id(budget.cycle_id) if budget.cycle_id else None,
        "category": budget.category,
        "amount": as_number(budget.amount),
        "periodStart": as_date(budget.period_start),
        "periodEnd": as_date(budget.period_end),
    }


def serialize_payment(payment):
    return {
        "id": as_id(payment.id),
        "type": payment.type,
        "amount": as_number(payment.amount),
        "date": as_date(payment.date),
        "linkedExpenseId": (
            as_id(payment.linked_expense_id)
            if payment.linked_expense_id
            else None
        ),
        "linkedSaleId": (
            as_id(payment.linked_sale_id) if payment.linked_sale_id else None
        ),
        "reference": payment.reference or None,
    }


def serialize_harvest(harvest):
    return {
        "id": as_id(harvest.id),
        "cycleId": as_id(harvest.cycle_id),
        "quantity": as_number(harvest.quantity),
        "unitId": as_id(harvest.unit_id),
        "date": as_date(harvest.date),
    }


def serialize_customer(customer):
    return {"id": as_id(customer.id), "name": customer.name}


def serialize_sale(sale):
    return {
        "id": as_id(sale.id),
        "customerId": as_id(sale.customer_id),
        "harvestId": as_id(sale.harvest_id),
        "quantity": as_number(sale.quantity),
        "unitPrice": as_number(sale.unit_price),
        "date": as_date(sale.date),
        "revenue": as_number(sale.revenue),
    }


def serialize_notification(notification):
    return {
        "id": as_id(notification.id),
        "type": notification.type,
        "message": notification.message,
        "read": notification.read,
        "createdAt": as_datetime(notification.created_at),
        "updatedAt": as_datetime(notification.updated_at),
    }


ISO_DATE_ERROR = "must be a valid calendar date."


def parse_date(value, field, required_message, invalid_message=None):
    if value is None:
        raise ValueError(required_message)
    text = str(value).strip()
    if not text:
        raise ValueError(required_message)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(invalid_message or required_message) from exc


def parse_decimal(
    value,
    field,
    required_message,
    not_numeric_message,
    *,
    negative_message=None,
    positive_message=None,
    allow_zero=True,
):
    if value is None:
        raise ValueError(required_message)
    if isinstance(value, bool):
        raise ValueError(not_numeric_message)
    text = str(value).strip() if not isinstance(value, (int, float)) else value
    if isinstance(text, str) and text == "":
        raise ValueError(required_message)
    try:
        number = Decimal(str(text))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(not_numeric_message) from exc
    if not number.is_finite():
        raise ValueError(not_numeric_message)
    if negative_message and number < 0:
        raise ValueError(negative_message)
    if positive_message and number <= 0:
        raise ValueError(positive_message)
    if not allow_zero and number == 0:
        raise ValueError(positive_message or not_numeric_message)
    return number
