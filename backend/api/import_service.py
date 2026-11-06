"""CSV and Excel import previews plus confirmed import commits.

The service parses an uploaded file, validates every data row, and flags
duplicates both inside the file and against existing farm records. A valid
preview is stored server-side behind a single-use token so the confirmation
step can persist only the rows the user selected. Previewing never creates
expense or stock movement records.
"""

import csv
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    CropCycle,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    ImportCommit,
    ImportPreview,
    InventoryItem,
    MovementType,
    StockMovement,
)

__all__ = [
    "ImportCommitError",
    "ImportFileError",
    "PREVIEW_TOKEN_TTL",
    "SUPPORTED_ENTITY_TYPES",
    "commit_import",
    "preview_import",
]

PREVIEW_TOKEN_TTL = timedelta(minutes=30)

SUPPORTED_ENTITY_TYPES = ("expenses", "inventory_movements")

# Canonical field -> accepted normalized header spellings.
_EXPENSE_COLUMNS = {
    "date": {"date"},
    "category": {"category"},
    "amount": {"amount"},
    "supplier": {"supplier"},
    "notes": {"note", "notes"},
    "cycleId": {"cycle", "cycleid"},
}
_MOVEMENT_COLUMNS = {
    "item": {"item", "itemname"},
    "type": {"type"},
    "quantity": {"quantity"},
    "date": {"date"},
    "note": {"note", "notes"},
}
_REQUIRED_FIELDS = {
    "expenses": ("date", "category", "amount"),
    "inventory_movements": ("item", "type", "quantity"),
}
_COLUMNS = {
    "expenses": _EXPENSE_COLUMNS,
    "inventory_movements": _MOVEMENT_COLUMNS,
}

CATEGORY_MESSAGE = (
    "Category must be one of: inputs, labour, equipment, overhead, other."
)
MOVEMENT_TYPE_MESSAGE = (
    "Type must be one of: purchase, usage, adjustment."
)

# The amount/quantity models use DecimalField(max_digits=14, decimal_places=4),
# which allows at most 10 integer digits and 4 fractional digits.
_MAX_ABSOLUTE_VALUE = Decimal("10000000000")
_MAX_VALUE_TEXT = "9999999999.9999"
_MAX_DECIMAL_PLACES = 4


class ImportFileError(ValueError):
    """Raised when a whole file cannot be read or is structurally invalid."""


class ImportCommitError(ValueError):
    """Raised when a preview cannot be committed as requested."""

    def __init__(self, message, field=None, status_code=400):
        super().__init__(message)
        self.message = message
        self.field = field
        self.status_code = status_code


def _cell_text(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value).strip()


def _is_blank(value):
    return _cell_text(value) == ""


def _trim_trailing_blanks(values):
    values = list(values)
    while values and _is_blank(values[-1]):
        values.pop()
    return values


def _normalize_header(value):
    text = _cell_text(value).lower()
    return re.sub(r"[\s_-]+", "", text)


def _read_csv(content):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError(
            "The file must be UTF-8 encoded."
        ) from exc
    if not text.strip():
        raise ImportFileError("The uploaded file is empty.")
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        rows = []
        previous_line = 0
        for row in reader:
            rows.append((previous_line + 1, list(row)))
            previous_line = reader.line_num
        return rows
    except csv.Error as exc:
        raise ImportFileError(
            f"The CSV file could not be parsed: {exc}."
        ) from exc


def _read_xlsx(content):
    if not content:
        raise ImportFileError("The uploaded file is empty.")
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(content), read_only=True, data_only=True
        )
    except Exception as exc:
        raise ImportFileError(
            "The Excel file could not be parsed. Upload a valid .xlsx file."
        ) from exc
    try:
        worksheet = workbook.active
        rows = [
            (row_number, list(values))
            for row_number, values in enumerate(
                worksheet.iter_rows(values_only=True), start=1
            )
        ]
    except Exception as exc:
        raise ImportFileError(
            "The Excel file could not be read. Upload a valid .xlsx file."
        ) from exc
    finally:
        workbook.close()
    if not rows or all(
        _is_blank(value) for _, row in rows for value in row
    ):
        raise ImportFileError("The uploaded file is empty.")
    return rows


def _read_table(entity_type, uploaded_file):
    name = getattr(uploaded_file, "name", "") or ""
    extension = Path(name).suffix.lower()
    content = uploaded_file.read()
    if isinstance(content, str):
        content = content.encode("utf-8")

    if extension == ".csv":
        raw_rows = _read_csv(content)
    elif extension == ".xlsx":
        raw_rows = _read_xlsx(content)
    else:
        raise ImportFileError(
            "Unsupported file type. Upload a .csv or .xlsx file."
        )

    if not raw_rows:
        raise ImportFileError("The uploaded file is empty.")

    raw_headers = _trim_trailing_blanks(raw_rows[0][1])
    if not raw_headers:
        raise ImportFileError("The header row is empty.")

    columns = _COLUMNS[entity_type]
    alias_lookup = {
        alias: canonical
        for canonical, aliases in columns.items()
        for alias in aliases
    }
    canonical_headers = []
    seen = {}
    problems = []
    for index, header in enumerate(raw_headers):
        raw = _cell_text(header)
        normalized = _normalize_header(header)
        canonical = alias_lookup.get(normalized)
        if canonical is None:
            problems.append(
                f'Unexpected header "{raw}" at column {index + 1}.'
            )
            continue
        if canonical in seen:
            problems.append(
                f'Duplicate header "{raw}" for field "{canonical}".'
            )
            continue
        seen[canonical] = index
        canonical_headers.append(canonical)

    missing = [
        field
        for field in _REQUIRED_FIELDS[entity_type]
        if field not in seen
    ]
    if missing:
        problems.append(
            "Missing required header(s): " + ", ".join(missing) + "."
        )
    if problems:
        raise ImportFileError(" ".join(problems))

    data_rows = []
    for line_number, row in raw_rows[1:]:
        values = _trim_trailing_blanks(row)
        if all(_is_blank(value) for value in values):
            continue
        data_rows.append((line_number, values))
    return seen, data_rows


def _parse_date_cell(value, required):
    if isinstance(value, datetime):
        return value.date(), None
    if isinstance(value, date):
        return value, None
    text = _cell_text(value)
    if not text:
        if required:
            return None, "Date is required."
        return None, None
    try:
        return date.fromisoformat(text), None
    except ValueError:
        return None, "Date must be a valid calendar date."


def _parse_positive_decimal(value, label):
    text = _cell_text(value)
    if not text:
        return None, f"{label} is required."
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, f"{label} must be a number."
    if not number.is_finite():
        return None, f"{label} must be a number."
    if number <= 0:
        return None, f"{label} must be greater than zero."
    if number >= _MAX_ABSOLUTE_VALUE:
        return (
            None,
            f"{label} must not exceed {_MAX_VALUE_TEXT}.",
        )
    exponent = number.normalize().as_tuple().exponent
    if exponent < -_MAX_DECIMAL_PLACES:
        return (
            None,
            f"{label} must have at most {_MAX_DECIMAL_PLACES} "
            "decimal places.",
        )
    return number, None


def _optional_text(value):
    text = _cell_text(value)
    return text or None


def _field_value(values, index, field):
    position = index.get(field)
    if position is None or position >= len(values):
        return None
    return values[position]


def _supplier_key(supplier):
    return (supplier or "").strip().casefold()


def _expense_key(expense_date, category, amount, supplier):
    return (expense_date, category, amount, _supplier_key(supplier))


def _movement_key(item_id, movement_type, quantity, movement_date, note):
    return (
        str(item_id),
        movement_type,
        quantity,
        movement_date,
        (note or "").strip(),
    )


def _existing_expense_keys(farm):
    keys = set()
    for row in Expense.objects.filter(farm=farm).values(
        "date", "category", "amount", "supplier"
    ):
        keys.add(
            _expense_key(
                row["date"],
                row["category"],
                row["amount"],
                row["supplier"],
            )
        )
    return keys


def _existing_movement_keys(farm):
    keys = set()
    for row in StockMovement.objects.filter(farm=farm).values(
        "item_id", "type", "quantity", "date", "note"
    ):
        keys.add(
            _movement_key(
                row["item_id"],
                row["type"],
                row["quantity"],
                row["date"],
                row["note"],
            )
        )
    return keys


def _item_lookup(farm):
    by_name = {}
    by_id = {}
    for item in InventoryItem.objects.filter(farm=farm).values("id", "name"):
        by_id[str(item["id"])] = item
        by_name.setdefault(item["name"].strip().casefold(), item)
    return by_name, by_id


def _resolve_cycle(farm, value):
    text = _cell_text(value)
    if not text:
        return None, None
    try:
        cycle = CropCycle.objects.filter(farm=farm, pk=text).first()
    except (ValidationError, ValueError, TypeError):
        cycle = None
    if cycle is None:
        return None, "The selected crop cycle does not exist."
    return cycle, None


def _validate_expense_row(values, index, farm, items_cache):
    errors = []
    raw_date = _field_value(values, index, "date")
    expense_date, date_error = _parse_date_cell(raw_date, required=True)
    if date_error:
        errors.append({"field": "date", "message": date_error})

    category = _cell_text(_field_value(values, index, "category")).lower()
    if not category:
        errors.append(
            {"field": "category", "message": "Category is required."}
        )
    elif category not in ExpenseCategory.values:
        errors.append(
            {"field": "category", "message": CATEGORY_MESSAGE}
        )

    raw_amount = _field_value(values, index, "amount")
    amount, amount_error = _parse_positive_decimal(raw_amount, "Amount")
    if amount_error:
        errors.append({"field": "amount", "message": amount_error})

    supplier = _optional_text(_field_value(values, index, "supplier"))
    notes = _optional_text(_field_value(values, index, "notes"))

    cycle, cycle_error = _resolve_cycle(
        farm, _field_value(values, index, "cycleId")
    )
    if cycle_error:
        errors.append({"field": "cycleId", "message": cycle_error})

    if errors:
        return None, errors

    data = {
        "date": expense_date.isoformat(),
        "category": category,
        "amount": amount,
        "supplier": supplier,
        "notes": notes,
        "cycleId": str(cycle.id) if cycle is not None else None,
    }
    key = _expense_key(expense_date, category, amount, supplier)
    return (data, key), None


def _validate_movement_row(values, index, farm, items_cache):
    errors = []
    by_name, by_id = items_cache
    raw_item = _cell_text(_field_value(values, index, "item"))
    item = None
    if not raw_item:
        errors.append({"field": "item", "message": "Item is required."})
    else:
        item = by_name.get(raw_item.casefold()) or by_id.get(raw_item)
        if item is None:
            errors.append(
                {
                    "field": "item",
                    "message": f'Unknown inventory item "{raw_item}".',
                }
            )

    movement_type = _cell_text(_field_value(values, index, "type")).lower()
    if not movement_type:
        errors.append({"field": "type", "message": "Type is required."})
    elif movement_type not in MovementType.values:
        errors.append({"field": "type", "message": MOVEMENT_TYPE_MESSAGE})

    raw_quantity = _field_value(values, index, "quantity")
    quantity, quantity_error = _parse_positive_decimal(
        raw_quantity, "Quantity"
    )
    if quantity_error:
        errors.append({"field": "quantity", "message": quantity_error})

    movement_date, date_error = _parse_date_cell(
        _field_value(values, index, "date"), required=True
    )
    if date_error:
        errors.append({"field": "date", "message": date_error})

    note = _optional_text(_field_value(values, index, "note"))

    if errors:
        return None, errors

    data = {
        "item": item["name"],
        "itemId": str(item["id"]),
        "type": movement_type,
        "quantity": quantity,
        "date": movement_date.isoformat() if movement_date else None,
        "note": note,
    }
    key = _movement_key(
        item["id"], movement_type, quantity, movement_date, note
    )
    return (data, key), None


def preview_import(farm, entity_type, uploaded_file):
    """Return a validated preview for a CSV or Excel upload.

    A server-side token stores the normalized rows so a later confirmation
    can commit them without trusting client data. ``uploaded_file`` must be a
    file-like object with a ``name`` and ``read`` method, such as a Django
    ``UploadedFile``. Structural file problems raise
    :class:`ImportFileError`; row problems are reported in the preview.
    """

    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise ImportFileError(
            "Unsupported import type. Use expenses or inventory_movements."
        )

    index, rows = _read_table(entity_type, uploaded_file)
    file_name = getattr(uploaded_file, "name", "") or ""

    if entity_type == "expenses":
        db_keys = _existing_expense_keys(farm)
        items_cache = None
        validator = _validate_expense_row
        duplicate_reason = "Duplicate of an existing expense."
    else:
        db_keys = _existing_movement_keys(farm)
        items_cache = _item_lookup(farm)
        validator = _validate_movement_row
        duplicate_reason = "Duplicate of an existing stock movement."

    valid_rows = []
    invalid_rows = []
    duplicate_rows = []
    stored_rows = []
    seen_in_file = {}

    for row_number, values in rows:
        if len(values) > len(index):
            invalid_rows.append(
                {
                    "row": row_number,
                    "errors": [
                        {
                            "field": "row",
                            "message": (
                                "Row has more values than the headers define."
                            ),
                        }
                    ],
                }
            )
            continue
        stored_rows.append(
            {
                "row": row_number,
                "values": [_cell_text(value) for value in values],
            }
        )
        result, errors = validator(values, index, farm, items_cache)
        if errors:
            invalid_rows.append({"row": row_number, "errors": errors})
            continue
        data, key = result
        if key in db_keys:
            duplicate_rows.append(
                {
                    "row": row_number,
                    "reason": duplicate_reason,
                    "key": _key_payload(entity_type, data),
                }
            )
            continue
        if key in seen_in_file:
            duplicate_rows.append(
                {
                    "row": row_number,
                    "reason": (
                        f"Duplicate of row {seen_in_file[key]} "
                        "in this file."
                    ),
                    "key": _key_payload(entity_type, data),
                }
            )
            continue
        seen_in_file[key] = row_number
        valid_rows.append({"row": row_number, **data})

    total = len(rows)
    preview = ImportPreview.objects.create(
        farm=farm,
        entity_type=entity_type,
        columns=index,
        rows=stored_rows,
        expires_at=timezone.now() + PREVIEW_TOKEN_TTL,
    )
    return {
        "entityType": entity_type,
        "fileName": file_name,
        "previewToken": str(preview.token),
        "expiresAt": preview.expires_at.isoformat(),
        "totalRows": total,
        "validRows": valid_rows,
        "invalidRows": invalid_rows,
        "duplicateRows": duplicate_rows,
        "counts": {
            "total": total,
            "valid": len(valid_rows),
            "invalid": len(invalid_rows),
            "duplicate": len(duplicate_rows),
        },
    }


def _key_payload(entity_type, data):
    if entity_type == "expenses":
        return {
            "date": data["date"],
            "category": data["category"],
            "amount": data["amount"],
            "supplier": data["supplier"],
        }
    return {
        "itemId": data["itemId"],
        "type": data["type"],
        "quantity": data["quantity"],
        "date": data["date"],
        "note": data["note"],
    }


def _alias_lookup(entity_type):
    return {
        alias: canonical
        for canonical, aliases in _COLUMNS[entity_type].items()
        for alias in aliases
    }


def _row_identifier(value):
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        row = value
    else:
        text = _cell_text(value)
        if not text:
            raise ValueError
        row = int(text)
    if row <= 0:
        raise ValueError
    return row


def _parse_corrections(corrections):
    if corrections is None:
        return {}
    if not isinstance(corrections, dict):
        raise ImportCommitError(
            "Corrections must be an object keyed by row number.",
            "corrections",
        )
    parsed = {}
    for key, values in corrections.items():
        try:
            row = _row_identifier(key)
        except (TypeError, ValueError):
            raise ImportCommitError(
                "Corrections must be keyed by a valid row number.",
                "corrections",
            )
        if not isinstance(values, dict):
            raise ImportCommitError(
                "Each correction must be an object of field values.",
                "corrections",
            )
        parsed[row] = values
    return parsed


def _parse_confirmation(confirmed_rows, corrections):
    if not isinstance(confirmed_rows, list) or not confirmed_rows:
        raise ImportCommitError(
            "Select at least one row to import.", "confirmedRows"
        )
    parsed = []
    seen = set()
    for entry in confirmed_rows:
        overrides = {}
        if isinstance(entry, dict):
            if "row" not in entry:
                raise ImportCommitError(
                    "Each confirmed row must include a row number.",
                    "confirmedRows",
                )
            raw_row = entry.get("row")
            values = entry.get("values", entry.get("corrections"))
            if values is not None:
                if not isinstance(values, dict):
                    raise ImportCommitError(
                        "Corrected values must be an object of field values.",
                        "confirmedRows",
                    )
                overrides.update(values)
        else:
            raw_row = entry
        try:
            row = _row_identifier(raw_row)
        except (TypeError, ValueError):
            raise ImportCommitError(
                "Each confirmed row must include a valid row number.",
                "confirmedRows",
            )
        if row in seen:
            raise ImportCommitError(
                f"Row {row} is confirmed more than once.", "confirmedRows"
            )
        overrides = {**corrections.get(row, {}), **overrides}
        seen.add(row)
        parsed.append((row, overrides))
    return parsed


def _apply_corrections(entity_type, values, index, overrides):
    values = list(values)
    index = dict(index)
    lookup = _alias_lookup(entity_type)
    for field, value in overrides.items():
        if field == "itemId":
            # Derived from the item name; never trust a client-supplied id.
            continue
        canonical = lookup.get(_normalize_header(field))
        if canonical is None:
            raise ImportCommitError(
                f'Field "{field}" cannot be corrected for this import.',
                "corrections",
            )
        position = index.get(canonical)
        if position is None:
            position = len(values)
            index[canonical] = position
        while len(values) <= position:
            values.append(None)
        values[position] = value
    return values, index


def _format_row_errors(row, errors):
    messages = "; ".join(
        f'{error["field"]}: {error["message"]}' for error in errors
    )
    return f"Row {row} could not be imported: {messages}"


def _get_preview(farm, token):
    if token in (None, ""):
        raise ImportCommitError("Preview token is required.", "token")
    try:
        preview = (
            ImportPreview.objects.select_for_update()
            .get(token=token, farm=farm)
        )
    except (
        ImportPreview.DoesNotExist,
        ValidationError,
        TypeError,
        ValueError,
    ):
        raise ImportCommitError(
            "The preview token is invalid.", "token"
        )
    if preview.consumed_at is not None:
        raise ImportCommitError(
            "This preview has already been imported and cannot be reused.",
            "token",
            status_code=409,
        )
    if preview.expires_at <= timezone.now():
        raise ImportCommitError(
            "This preview has expired. Upload the file again to continue.",
            "token",
        )
    return preview


def _stored_index(columns):
    return {
        str(key): int(value) for key, value in (columns or {}).items()
    }


def _create_expense(farm, data):
    return Expense.objects.create(
        farm=farm,
        cycle_id=data["cycleId"] or None,
        category=data["category"],
        amount=data["amount"],
        date=date.fromisoformat(data["date"]),
        supplier=data["supplier"],
        notes=data["notes"],
        status=ExpenseStatus.DRAFT,
    )


def _create_movement(farm, data):
    return StockMovement.objects.create(
        farm=farm,
        item_id=data["itemId"],
        type=data["type"],
        quantity=data["quantity"],
        date=date.fromisoformat(data["date"]),
        note=data["note"] or "",
    )


def commit_import(farm, actor, token, confirmed_rows, corrections=None):
    """Persist only the confirmed rows from a server-side preview.

    ``confirmed_rows`` is a list of preview row numbers. Items may also be
    objects with a ``row`` key and optional ``values``/``corrections``
    mapping. ``corrections`` is a top-level object keyed by row number. The
    preview token is consumed only after a successful import.
    """

    if token in (None, ""):
        raise ImportCommitError("Preview token is required.", "token")
    if not isinstance(confirmed_rows, list) or not confirmed_rows:
        raise ImportCommitError(
            "Select at least one row to import.", "confirmedRows"
        )
    corrections = _parse_corrections(corrections)

    with transaction.atomic():
        preview = _get_preview(farm, token)
        selections = _parse_confirmation(confirmed_rows, corrections)
        index = _stored_index(preview.columns)
        stored = {row["row"]: row["values"] for row in preview.rows}
        if preview.entity_type == "expenses":
            validator = _validate_expense_row
            items_cache = None
            db_keys = _existing_expense_keys(farm)
        else:
            validator = _validate_movement_row
            items_cache = _item_lookup(farm)
            db_keys = _existing_movement_keys(farm)

        pending = []
        confirmed_keys = set()
        for row, overrides in selections:
            if row not in stored:
                raise ImportCommitError(
                    f"Row {row} is not part of this preview.",
                    "confirmedRows",
                )
            values, row_index = _apply_corrections(
                preview.entity_type, stored[row], index, overrides
            )
            result, errors = validator(
                values, row_index, farm, items_cache
            )
            if errors:
                raise ImportCommitError(
                    _format_row_errors(row, errors), "confirmedRows"
                )
            data, key = result
            if key in db_keys:
                raise ImportCommitError(
                    f"Row {row} duplicates an existing record.",
                    "confirmedRows",
                )
            if key in confirmed_keys:
                raise ImportCommitError(
                    f"Row {row} duplicates another confirmed row.",
                    "confirmedRows",
                )
            confirmed_keys.add(key)
            pending.append((row, data))

        created = []
        for row, data in pending:
            if preview.entity_type == "expenses":
                instance = _create_expense(farm, data)
            else:
                instance = _create_movement(farm, data)
            created.append((row, instance))

        preview.consumed_at = timezone.now()
        preview.save(update_fields=["consumed_at"])
        audit = ImportCommit.objects.create(
            farm=farm,
            actor=actor,
            preview_token=preview.token,
            entity_type=preview.entity_type,
            entity_counts={preview.entity_type: len(created)},
        )

    return {
        "previewToken": str(preview.token),
        "entityType": preview.entity_type,
        "imported": [
            {"row": row, "id": str(instance.id)}
            for row, instance in created
        ],
        "counts": {
            "confirmed": len(pending),
            "imported": len(created),
            "skipped": max(0, len(preview.rows) - len(pending)),
        },
        "audit": {
            "id": str(audit.id),
            "actorId": str(audit.actor_id),
            "committedAt": audit.created_at.isoformat(),
            "entityCounts": audit.entity_counts,
            "previewToken": str(audit.preview_token),
        },
    }
