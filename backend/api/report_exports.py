import csv
import json
import re
from dataclasses import dataclass
from io import BytesIO, StringIO

from django.http import HttpResponse
from openpyxl import Workbook

from .exceptions import ApiError


@dataclass(frozen=True)
class ReportTable:
    name: str
    headers: tuple[str, ...]
    rows: tuple[tuple, ...]


@dataclass(frozen=True)
class NormalizedReport:
    tables: tuple[ReportTable, ...]


_EMPTY_HEADERS = {
    "profitability": {
        "crop_cycle": (
            "cycleId",
            "fieldId",
            "fieldName",
            "cropId",
            "cropName",
            "startDate",
            "endDate",
            "revenue",
            "directCosts",
            "allocatedOverheads",
            "operatingSurplus",
            "resultAfterAllocatedOverheads",
        ),
        "field": (
            "fieldId",
            "fieldName",
            "cycleCount",
            "revenue",
            "directCosts",
            "allocatedOverheads",
            "operatingSurplus",
            "resultAfterAllocatedOverheads",
        ),
        "season": (
            "seasonId",
            "name",
            "startDate",
            "endDate",
            "cycles",
            "revenue",
            "directCosts",
            "allocatedOverheads",
            "operatingSurplus",
            "resultAfterAllocatedOverheads",
        ),
        "farm": (
            "farmId",
            "farmName",
            "cycleCount",
            "cycles",
            "revenue",
            "directCosts",
            "allocatedOverheads",
            "operatingSurplus",
            "resultAfterAllocatedOverheads",
        ),
    },
    "budget-vs-actual": {
        "overall": (
            "budgetId",
            "cycleId",
            "category",
            "budget",
            "actual",
            "variance",
            "variancePercentage",
            "periodStart",
            "periodEnd",
        ),
        "categories": (
            "budgetId",
            "cycleId",
            "category",
            "budget",
            "actual",
            "variance",
            "variancePercentage",
            "periodStart",
            "periodEnd",
        ),
    },
    "inventory": {
        "items": (
            "itemId",
            "name",
            "unitId",
            "currentQuantity",
            "reorderLevel",
            "lowStock",
        )
    },
    "labour-usage": {
        "rows": (
            "cycleId",
            "workerId",
            "workerName",
            "hours",
            "cost",
        )
    },
    "equipment-usage": {
        "rows": (
            "cycleId",
            "equipmentId",
            "equipmentName",
            "hours",
            "cost",
        )
    },
    "dashboard": {
        "unsoldProduce": ("cycleId", "quantity", "unitId")
    },
}

_DISPLAY_NAMES = {
    "activity-status": "Activity Status",
    "budget-vs-actual": "Budget vs Actual",
    "dashboard": "Dashboard",
    "equipment-usage": "Equipment Usage",
    "inventory": "Inventory",
    "labour-usage": "Labour Usage",
    "profitability": "Profitability",
    "items": "Items",
    "overall": "Overall",
    "categories": "Categories",
    "rows": "Rows",
    "unsoldProduce": "Unsold Produce",
    "summary": "Summary",
}


def _display_name(value):
    return _DISPLAY_NAMES.get(value, value.replace("-", " ").title())


def _cell_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _record_value(record, key):
    if isinstance(record, dict):
        return record.get(key)
    return record if key == "value" else None


def _record_table(name, records, empty_headers=()):
    records = list(records)
    if not records:
        headers = tuple(empty_headers)
        return ReportTable(name, headers, ())

    headers = []
    for record in records:
        if isinstance(record, dict):
            for key in record:
                if key not in headers:
                    headers.append(key)
        elif "value" not in headers:
            headers.append("value")
    rows = tuple(
        tuple(
            _cell_value(_record_value(record, key)) for key in headers
        )
        for record in records
    )
    return ReportTable(name, tuple(headers), rows)


def _flatten_summary(value, prefix="", result=None):
    if result is None:
        result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, list):
                result[path] = _cell_value(child)
            elif isinstance(child, dict):
                _flatten_summary(child, path, result)
            else:
                result[path] = child
    elif prefix:
        result[prefix] = _cell_value(value)
    return result


def _empty_headers(report_name, table_name, filters):
    if report_name == "profitability":
        grouping = str(
            filters.get("group_by", "crop_cycle") or "crop_cycle"
        ).strip().lower()
        return _EMPTY_HEADERS["profitability"].get(
            grouping, _EMPTY_HEADERS["profitability"]["crop_cycle"]
        )
    if report_name in ("labour-usage", "equipment-usage") and table_name == "rows":
        group_key = (
            "activityId"
            if filters.get("groupBy") == "activity"
            else "cycleId"
        )
        subject = (
            "worker"
            if report_name == "labour-usage"
            else "equipment"
        )
        return (
            group_key,
            f"{subject}Id",
            f"{subject}Name",
            "hours",
            "cost",
        )
    return _EMPTY_HEADERS.get(report_name, {}).get(table_name, ())


def normalize_report(report_name, payload, filters=None):
    """Convert a report payload into ordered worksheet-ready tables."""
    filters = filters or {}
    if isinstance(payload, list):
        return NormalizedReport(
            (
                _record_table(
                    report_name,
                    payload,
                    _empty_headers(report_name, report_name, filters),
                ),
            )
        )

    if not isinstance(payload, dict):
        payload = {"value": payload}

    tables = []
    summary = {}
    for key, value in payload.items():
        if isinstance(value, list):
            tables.append(
                _record_table(
                    report_name if key == "rows" else key,
                    value,
                    _empty_headers(report_name, key, filters),
                )
            )
        elif isinstance(value, dict):
            summary.update(_flatten_summary({key: value}))
        else:
            summary[key] = value

    if summary or not tables:
        tables.append(
            _record_table(
                "summary" if tables else report_name,
                [summary],
                tuple(summary),
            )
        )

    return NormalizedReport(tuple(tables))


def _safe_sheet_name(name, existing):
    base = re.sub(r"[\\/*?:\[\]]", " ", _display_name(name)).strip()
    base = (base or "Report")[:31]
    candidate = base
    suffix = 2
    while candidate.casefold() in existing:
        ending = f" {suffix}"
        candidate = f"{base[: 31 - len(ending)]}{ending}"
        suffix += 1
    existing.add(candidate.casefold())
    return candidate


def serialize_csv(report):
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    for index, table in enumerate(report.tables):
        if index:
            writer.writerow([])
            writer.writerow([f"Table: {_display_name(table.name)}"])
        writer.writerow(table.headers)
        writer.writerows(table.rows)
    return output.getvalue().encode("utf-8")


def serialize_xlsx(report):
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheet_names = set()
    for table in report.tables:
        worksheet = workbook.create_sheet(
            _safe_sheet_name(table.name, sheet_names)
        )
        if table.headers:
            worksheet.append(table.headers)
            for row in table.rows:
                worksheet.append(row)
    if not workbook.sheetnames:
        workbook.create_sheet("Report")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_report_export(report_name, payload, file_format, filters=None):
    normalized = normalize_report(report_name, payload, filters)
    if file_format == "csv":
        content = serialize_csv(normalized)
        content_type = "text/csv; charset=utf-8"
        extension = "csv"
    elif file_format == "xlsx":
        content = serialize_xlsx(normalized)
        content_type = (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
        extension = "xlsx"
    else:
        raise ApiError(
            "exportFormat must be either csv or xlsx.",
            400,
            "exportFormat",
        )

    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = (
        f'attachment; filename="agrivanta-{report_name}.{extension}"'
    )
    return response


def report_payload(report_name, farm, query_params):
    if report_name == "profitability":
        from .reporting import aggregate_profitability

        return aggregate_profitability(
            farm, query_params.get("group_by")
        )
    if report_name == "budget-vs-actual":
        from .budget_reports import budget_vs_actual_report

        return budget_vs_actual_report(farm, query_params)
    if report_name == "dashboard":
        from .dashboard import dashboard_for_request

        return dashboard_for_request(farm, query_params)

    from . import operational_reports

    functions = {
        "activity-status": operational_reports.activity_status_report,
        "inventory": operational_reports.inventory_report,
        "labour-usage": operational_reports.labour_usage_report,
        "equipment-usage": operational_reports.equipment_usage_report,
    }
    report_function = functions.get(report_name)
    if report_function is None:
        raise ApiError("That report does not exist.", 404, "report")
    return report_function(farm, query_params)
