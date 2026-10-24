from decimal import Decimal

from django.core.exceptions import ValidationError

from .exceptions import ApiError
from .models import CropCycle, Harvest, Sale
from .views import _convert_quantity_between_units, aggregate_harvest_quantity_for_cycle


def report_crop_cycle(farm, cycle):
    if cycle is None:
        raise ApiError("That crop cycle no longer exists.")
    # Check farm ownership - could be passed as id or instance
    cycle_farm_id = getattr(cycle, "farm_id", None)
    farm_id = getattr(farm, "id", farm)
    if cycle_farm_id != farm_id:
        raise ApiError("That crop cycle no longer exists.")
    try:
        cycle = CropCycle.objects.get(pk=getattr(cycle, "pk", cycle), farm=farm)
    except (CropCycle.DoesNotExist, ValueError, ValidationError):
        raise ApiError("That crop cycle no longer exists.")

    harvests = list(
        Harvest.objects.filter(farm=farm, cycle=cycle)
        .select_related("unit")
        .order_by("created_at", "id")
    )

    sales = list(
        Sale.objects.filter(farm=farm, harvest__cycle=cycle)
        .select_related("harvest", "harvest__unit")
        .order_by("created_at", "id")
    )

    if not harvests and not sales:
        return {
            "cycleId": str(cycle.id),
            "harvestedQuantity": Decimal(0),
            "soldQuantity": Decimal(0),
            "unsoldQuantity": Decimal(0),
            "revenue": Decimal(0),
            "unitId": None,
        }

    if harvests:
        total_harvested, unit = aggregate_harvest_quantity_for_cycle(farm, cycle)
    else:
        total_harvested = Decimal(0)
        unit = None

    if unit is None and harvests:
        unit = harvests[0].unit
    elif unit is None and sales:
        if sales and sales[0].harvest and sales[0].harvest.unit_id:
            unit = sales[0].harvest.unit
        else:
            return {
                "cycleId": str(cycle.id),
                "harvestedQuantity": Decimal(0),
                "soldQuantity": Decimal(0),
                "unsoldQuantity": Decimal(0),
                "revenue": Decimal(0),
                "unitId": None,
            }

    total_sold = Decimal(0)
    total_revenue = Decimal(0)
    for sale in sales:
        sold_converted = _convert_quantity_between_units(
            farm, sale.quantity, sale.harvest.unit, unit
        )
        total_sold += sold_converted
        total_revenue += sale.revenue

    if total_sold > total_harvested:
        raise ApiError(
            f"Stored sales exceed stored harvests for crop cycle {cycle.id}."
        )

    unsold_quantity = total_harvested - total_sold
    return {
        "cycleId": str(cycle.id),
        "harvestedQuantity": total_harvested,
        "soldQuantity": total_sold,
        "unsoldQuantity": unsold_quantity,
        "revenue": total_revenue,
        "unitId": str(unit.id) if unit is not None else None,
    }
