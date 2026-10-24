from decimal import Decimal

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ApiError
from .models import (
    Activity,
    ActivityCategory,
    ActivityInputNeed,
    ActivityStatus,
    ActivityType,
    Attachment,
    BaseMeasure,
    Crop,
    CropCycle,
    CycleStatus,
    Customer,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Farm,
    Field,
    Harvest,
    InventoryItem,
    MovementType,
    Payment,
    PaymentType,
    Sale,
    StockMovement,
    Unit,
    UnitConversion,
    User,
    Variety,
)
from .serializers import (
    as_date,
    as_number,
    cycle_label,
    parse_date,
    parse_decimal,
    serialize_activity,
    serialize_activity_type,
    serialize_attachment,
    serialize_conversion,
    serialize_crop,
    serialize_cycle,
    serialize_cycle_ref,
    serialize_customer,
    serialize_expense,
    serialize_farm,
    serialize_field,
    serialize_harvest,
    serialize_inventory_item,
    serialize_movement,
    serialize_payment,
    serialize_sale,
    serialize_unit,
    serialize_user,
    serialize_variety,
)

STANDARD_ACTIVITY_TEMPLATES = [
    ("Land preparation", ActivityCategory.LAND_PREPARATION),
    ("Planting", ActivityCategory.PLANTING),
    ("Fertilizing", ActivityCategory.FERTILIZING),
    ("Spraying", ActivityCategory.SPRAYING),
    ("Harvesting", ActivityCategory.HARVESTING),
]

DEFAULT_CUSTOMER_NAMES = ["Greenfield Grain Co.", "Harbour Mill"]

ACTIVITY_TRANSITIONS = {
    ActivityStatus.PLANNED: [ActivityStatus.IN_PROGRESS],
    ActivityStatus.IN_PROGRESS: [ActivityStatus.COMPLETED],
    ActivityStatus.OVERDUE: [ActivityStatus.IN_PROGRESS],
    ActivityStatus.COMPLETED: [],
}


def require_text(data, key, message):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(message, status.HTTP_400_BAD_REQUEST, key)
    return value.strip()


def optional_text(data, key):
    value = data.get(key)
    if value is None:
        return ""
    return str(value).strip()


def get_farm(user):
    farm = getattr(user, "farm", None)
    if farm is None:
        raise ApiError(
            "No farm is configured.", status.HTTP_404_NOT_FOUND
        )
    return farm


def scoped_get(model, farm, pk, message, field=None):
    if pk in (None, ""):
        raise ApiError(
            message, status.HTTP_400_BAD_REQUEST, field or "id"
        )
    try:
        return model.objects.get(farm=farm, pk=pk)
    except (model.DoesNotExist, ValueError, ValidationError):
        raise ApiError(message, status.HTTP_404_NOT_FOUND, field)


def parse_body_date(data, key, required_message, invalid_message=None):
    try:
        return parse_date(
            data.get(key), key, required_message, invalid_message
        )
    except ValueError as exc:
        raise ApiError(
            str(exc), status.HTTP_400_BAD_REQUEST, key
        )


def parse_body_decimal(
    data,
    key,
    required_message,
    not_numeric_message,
    **kwargs,
):
    try:
        return parse_decimal(
            data.get(key),
            key,
            required_message,
            not_numeric_message,
            **kwargs,
        )
    except ValueError as exc:
        raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST, key)


def seed_farm(farm):
    ActivityType.objects.bulk_create(
        [
            ActivityType(
                farm=farm,
                name=name,
                category=category,
                standard=True,
            )
            for name, category in STANDARD_ACTIVITY_TEMPLATES
        ]
    )
    Customer.objects.bulk_create(
        [Customer(farm=farm, name=name) for name in DEFAULT_CUSTOMER_NAMES]
    )


def format_amount(value):
    return f"{value:.4f}".rstrip("0").rstrip(".")


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        email = str(data.get("email") or "").strip().lower()
        password = data.get("password")

        if not email:
            raise ApiError(
                "Email is required.", status.HTTP_400_BAD_REQUEST, "email"
            )
        try:
            validate_email(email)
        except ValidationError:
            raise ApiError(
                "Enter a valid email address.",
                status.HTTP_400_BAD_REQUEST,
                "email",
            )
        if not isinstance(password, str) or not password:
            raise ApiError(
                "Password is required.",
                status.HTTP_400_BAD_REQUEST,
                "password",
            )
        if User.objects.filter(email__iexact=email).exists():
            raise ApiError(
                "An account with that email already exists.",
                status.HTTP_409_CONFLICT,
                "email",
            )

        name = str(data.get("name") or "").strip()
        with transaction.atomic():
            user = User.objects.create_user(
                email=email, password=password, name=name
            )
            farm = Farm.objects.create(
                owner=user,
                name=f"{name}'s Farm" if name else "My Farm",
                reporting_currency="USD",
            )
            seed_farm(farm)
            token = Token.objects.create(user=user)

        return Response(
            {"token": token.key, "user": serialize_user(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get("email") or "").strip().lower()
        password = request.data.get("password")

        user = authenticate(
            request=request, username=email, password=password
        )
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": serialize_user(user)})


class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(serialize_user(request.user))


class FarmView(APIView):
    def get(self, request):
        return Response(serialize_farm(get_farm(request.user)))

    def put(self, request):
        farm = get_farm(request.user)
        name = require_text(
            request.data, "name", "Farm name is required."
        )
        currency = request.data.get("reportingCurrency")
        currency = str(currency).strip() if currency is not None else ""
        if (
            len(currency) != 3
            or not currency.isalpha()
        ):
            raise ApiError(
                "Reporting currency must be a three-letter code such as USD.",
                status.HTTP_400_BAD_REQUEST,
                "reportingCurrency",
            )
        farm.name = name
        farm.reporting_currency = currency.upper()
        farm.save(update_fields=["name", "reporting_currency"])
        return Response(serialize_farm(farm))


class FieldListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_field(field) for field in farm.fields.all()]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_text(
            request.data, "name", "Field name is required."
        )
        area = parse_body_decimal(
            request.data,
            "area",
            "Area must be a number.",
            "Area must be a number.",
            negative_message="Area cannot be negative.",
        )
        field = Field.objects.create(
            farm=farm,
            name=name,
            area=area,
            notes=optional_text(request.data, "notes"),
        )
        return Response(
            serialize_field(field), status=status.HTTP_201_CREATED
        )


class FieldDetailView(APIView):
    def put(self, request, field_id):
        farm = get_farm(request.user)
        field = scoped_get(
            Field, farm, field_id, "That field no longer exists."
        )
        name = require_text(
            request.data, "name", "Field name is required."
        )
        area = parse_body_decimal(
            request.data,
            "area",
            "Area must be a number.",
            "Area must be a number.",
            negative_message="Area cannot be negative.",
        )
        field.name = name
        field.area = area
        field.notes = optional_text(request.data, "notes")
        field.save()
        return Response(serialize_field(field))


class CropListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_crop(crop) for crop in farm.crops.all()]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_text(
            request.data, "name", "Crop name is required."
        )
        if Crop.objects.filter(farm=farm, name__iexact=name).exists():
            raise ApiError(
                f'A crop named "{name}" already exists.',
                status.HTTP_409_CONFLICT,
                "name",
            )
        crop = Crop.objects.create(farm=farm, name=name)
        return Response(
            serialize_crop(crop), status=status.HTTP_201_CREATED
        )


class CropDetailView(APIView):
    def put(self, request, crop_id):
        farm = get_farm(request.user)
        crop = scoped_get(
            Crop, farm, crop_id, "That crop no longer exists."
        )
        name = require_text(
            request.data, "name", "Crop name is required."
        )
        if (
            Crop.objects.filter(farm=farm, name__iexact=name)
            .exclude(pk=crop.pk)
            .exists()
        ):
            raise ApiError(
                f'A crop named "{name}" already exists.',
                status.HTTP_409_CONFLICT,
                "name",
            )
        crop.name = name
        crop.save(update_fields=["name"])
        return Response(serialize_crop(crop))


class VarietyListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        varieties = farm.varieties.all()
        crop_id = request.query_params.get("crop")
        if crop_id:
            varieties = varieties.filter(crop_id=crop_id)
        return Response(
            [serialize_variety(variety) for variety in varieties]
        )

    def post(self, request):
        farm = get_farm(request.user)
        crop = self._crop(farm, request.data.get("cropId"))
        name = require_text(
            request.data, "name", "Variety name is required."
        )
        variety = Variety.objects.create(
            farm=farm, crop=crop, name=name
        )
        return Response(
            serialize_variety(variety), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _crop(farm, crop_id):
        if crop_id in (None, ""):
            raise ApiError(
                "Select a crop for this variety.",
                status.HTTP_400_BAD_REQUEST,
                "cropId",
            )
        try:
            return Crop.objects.get(farm=farm, pk=crop_id)
        except (Crop.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected crop does not exist.",
                status.HTTP_404_NOT_FOUND,
                "cropId",
            )


class VarietyDetailView(APIView):
    def put(self, request, variety_id):
        farm = get_farm(request.user)
        variety = scoped_get(
            Variety, farm, variety_id, "That variety no longer exists."
        )
        crop = VarietyListView._crop(farm, request.data.get("cropId"))
        name = require_text(
            request.data, "name", "Variety name is required."
        )
        variety.crop = crop
        variety.name = name
        variety.save(update_fields=["crop", "name"])
        return Response(serialize_variety(variety))


class UnitListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_unit(unit) for unit in farm.units.all()]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_text(
            request.data, "name", "Unit name is required."
        )
        base_measure = self._base_measure(request.data.get("baseMeasure"))
        if Unit.objects.filter(farm=farm, name__iexact=name).exists():
            raise ApiError(
                f'A unit named "{name}" already exists.',
                status.HTTP_409_CONFLICT,
                "name",
            )
        unit = Unit.objects.create(
            farm=farm, name=name, base_measure=base_measure
        )
        return Response(
            serialize_unit(unit), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _base_measure(value):
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ApiError(
                "A base measure category (mass, volume, or count) is required.",
                status.HTTP_400_BAD_REQUEST,
                "baseMeasure",
            )
        if text not in BaseMeasure.values:
            raise ApiError(
                "Base measure must be one of: mass, volume, count.",
                status.HTTP_400_BAD_REQUEST,
                "baseMeasure",
            )
        return text


class UnitDetailView(APIView):
    def put(self, request, unit_id):
        farm = get_farm(request.user)
        unit = scoped_get(
            Unit, farm, unit_id, "That unit no longer exists."
        )
        name = require_text(
            request.data, "name", "Unit name is required."
        )
        base_measure = UnitListView._base_measure(
            request.data.get("baseMeasure")
        )
        if (
            Unit.objects.filter(farm=farm, name__iexact=name)
            .exclude(pk=unit.pk)
            .exists()
        ):
            raise ApiError(
                f'A unit named "{name}" already exists.',
                status.HTTP_409_CONFLICT,
                "name",
            )
        unit.name = name
        unit.base_measure = base_measure
        unit.save(update_fields=["name", "base_measure"])
        return Response(serialize_unit(unit))


def unit_lookup(farm, unit_id, field):
    if unit_id in (None, ""):
        raise ApiError(
            "Select a unit.", status.HTTP_400_BAD_REQUEST, field
        )
    try:
        return Unit.objects.get(farm=farm, pk=unit_id)
    except (Unit.DoesNotExist, ValueError, ValidationError):
        raise ApiError(
            "That unit does not exist.",
            status.HTTP_404_NOT_FOUND,
            field,
        )


class ConversionListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_conversion(conversion)
                for conversion in farm.conversions.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        from_unit = unit_lookup(
            farm, request.data.get("fromUnitId"), "fromUnitId"
        )
        to_unit = unit_lookup(
            farm, request.data.get("toUnitId"), "toUnitId"
        )
        if from_unit.pk == to_unit.pk:
            raise ApiError(
                "Choose two different units.",
                status.HTTP_400_BAD_REQUEST,
                "toUnitId",
            )
        try:
            factor = parse_decimal(
                request.data.get("factor"),
                "factor",
                "Conversion factor must be a positive number.",
                "Conversion factor must be a positive number.",
                positive_message="Conversion factor must be a positive number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "factor"
            )
        if UnitConversion.objects.filter(
            farm=farm, from_unit=from_unit, to_unit=to_unit
        ).exists():
            raise ApiError(
                f'A conversion rule from "{from_unit.name}" to '
                f'"{to_unit.name}" already exists.',
                status.HTTP_409_CONFLICT,
            )
        conversion = UnitConversion.objects.create(
            farm=farm,
            from_unit=from_unit,
            to_unit=to_unit,
            factor=factor,
        )
        return Response(
            serialize_conversion(conversion),
            status=status.HTTP_201_CREATED,
        )


class ConversionConvertView(APIView):
    def post(self, request):
        farm = get_farm(request.user)
        from_unit = unit_lookup(
            farm, request.data.get("fromUnitId"), "fromUnitId"
        )
        to_unit = unit_lookup(
            farm, request.data.get("toUnitId"), "toUnitId"
        )
        try:
            quantity = parse_decimal(
                request.data.get("quantity"),
                "quantity",
                "Quantity must be a number.",
                "Quantity must be a number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
            )

        if from_unit.pk == to_unit.pk:
            return Response(
                {
                    "fromUnitId": str(from_unit.id),
                    "toUnitId": str(to_unit.id),
                    "quantity": as_number(quantity),
                    "factor": 1,
                    "converted": as_number(quantity),
                }
            )

        if from_unit.base_measure != to_unit.base_measure:
            raise ApiError(
                f'Cannot convert "{from_unit.name}" '
                f"({from_unit.base_measure}) to \"{to_unit.name}\" "
                f"({to_unit.base_measure}): base measures do not match.",
                status.HTTP_400_BAD_REQUEST,
            )

        forward = UnitConversion.objects.filter(
            farm=farm, from_unit=from_unit, to_unit=to_unit
        ).first()
        if forward is not None:
            factor = forward.factor
            converted = quantity * factor
        else:
            reverse = UnitConversion.objects.filter(
                farm=farm, from_unit=to_unit, to_unit=from_unit
            ).first()
            if reverse is None:
                raise ApiError(
                    f'No rule exists for converting from '
                    f'"{from_unit.name}" to "{to_unit.name}".',
                    status.HTTP_404_NOT_FOUND,
                )
            factor = Decimal(1) / reverse.factor
            converted = quantity / reverse.factor

        return Response(
            {
                "fromUnitId": str(from_unit.id),
                "toUnitId": str(to_unit.id),
                "quantity": as_number(quantity),
                "factor": as_number(factor),
                "converted": as_number(converted),
            }
        )


class CropCycleListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        cycles = farm.crop_cycles.select_related(
            "field", "crop", "variety"
        )
        field_id = request.query_params.get("field")
        if field_id:
            cycles = cycles.filter(field_id=field_id)
        return Response([serialize_cycle(cycle) for cycle in cycles])

    def post(self, request):
        farm = get_farm(request.user)
        field = self._field(farm, request.data.get("fieldId"))
        crop = self._crop(farm, request.data.get("cropId"))
        variety = self._variety(farm, request.data.get("varietyId"))
        if variety.crop_id != crop.id:
            raise ApiError(
                "The selected variety does not belong to the selected crop.",
                status.HTTP_400_BAD_REQUEST,
                "varietyId",
            )
        start_date = parse_body_date(
            request.data,
            "startDate",
            "Start date is required.",
            "Start date must be a valid calendar date.",
        )
        end_date = self._end_date(
            request.data.get("endDate"), start_date
        )
        expected_yield = self._optional_amount(
            request.data, "expectedYield"
        )
        expected_price = self._optional_amount(
            request.data, "expectedPrice"
        )
        cycle = CropCycle.objects.create(
            farm=farm,
            field=field,
            crop=crop,
            variety=variety,
            start_date=start_date,
            end_date=end_date,
            expected_yield=expected_yield,
            expected_price=expected_price,
            status=CycleStatus.OPEN,
        )
        return Response(
            serialize_cycle(cycle), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _field(farm, field_id):
        if field_id in (None, ""):
            raise ApiError(
                "Select a field for this crop cycle.",
                status.HTTP_400_BAD_REQUEST,
                "fieldId",
            )
        try:
            return Field.objects.get(farm=farm, pk=field_id)
        except (Field.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected field does not exist.",
                status.HTTP_404_NOT_FOUND,
                "fieldId",
            )

    @staticmethod
    def _crop(farm, crop_id):
        if crop_id in (None, ""):
            raise ApiError(
                "Select a crop for this crop cycle.",
                status.HTTP_400_BAD_REQUEST,
                "cropId",
            )
        try:
            return Crop.objects.get(farm=farm, pk=crop_id)
        except (Crop.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected crop does not exist.",
                status.HTTP_404_NOT_FOUND,
                "cropId",
            )

    @staticmethod
    def _variety(farm, variety_id):
        if variety_id in (None, ""):
            raise ApiError(
                "Select a variety for this crop cycle.",
                status.HTTP_400_BAD_REQUEST,
                "varietyId",
            )
        try:
            return Variety.objects.get(farm=farm, pk=variety_id)
        except (Variety.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected variety does not exist.",
                status.HTTP_404_NOT_FOUND,
                "varietyId",
            )

    @staticmethod
    def _end_date(value, start_date):
        if value in (None, ""):
            return None
        try:
            end_date = parse_date(
                value,
                "endDate",
                "End date must be a valid calendar date.",
                "End date must be a valid calendar date.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc),
                status.HTTP_400_BAD_REQUEST,
                "endDate",
            )
        if end_date < start_date:
            raise ApiError(
                "End date cannot be before the start date.",
                status.HTTP_400_BAD_REQUEST,
                "endDate",
            )
        return end_date

    @staticmethod
    def _optional_amount(data, key):
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            return parse_decimal(
                value,
                key,
                f"{'Expected yield' if key == 'expectedYield' else 'Expected price'} must be a number.",
                f"{'Expected yield' if key == 'expectedYield' else 'Expected price'} must be a number.",
                negative_message=(
                    "Expected yield cannot be negative."
                    if key == "expectedYield"
                    else "Expected price cannot be negative."
                ),
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, key
            )


class CropCycleDetailView(APIView):
    def put(self, request, cycle_id):
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be edited.",
                status.HTTP_409_CONFLICT,
            )
        if "expectedYield" in request.data:
            cycle.expected_yield = CropCycleListView._optional_amount(
                request.data, "expectedYield"
            )
        if "expectedPrice" in request.data:
            cycle.expected_price = CropCycleListView._optional_amount(
                request.data, "expectedPrice"
            )
        cycle.save(update_fields=["expected_yield", "expected_price"])
        return Response(serialize_cycle(cycle))


class CropCycleCloseView(APIView):
    def post(self, request, cycle_id):
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is already closed.",
                status.HTTP_409_CONFLICT,
            )
        cycle.status = CycleStatus.CLOSED
        cycle.save(update_fields=["status"])
        return Response(serialize_cycle(cycle))


class ActivityTypeListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_activity_type(activity_type)
                for activity_type in farm.activity_types.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_text(
            request.data, "name", "Template name is required."
        )
        category = self._category(request.data.get("category"))
        if ActivityType.objects.filter(
            farm=farm, name__iexact=name
        ).exists():
            raise ApiError(
                f'A template named "{name}" already exists.',
                status.HTTP_409_CONFLICT,
                "name",
            )
        activity_type = ActivityType.objects.create(
            farm=farm, name=name, category=category, standard=False
        )
        return Response(
            serialize_activity_type(activity_type),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _category(value):
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ApiError(
                "A template category is required.",
                status.HTTP_400_BAD_REQUEST,
                "category",
            )
        if text not in ActivityCategory.values:
            raise ApiError(
                "Category must be one of: land preparation, planting, "
                "fertilizing, spraying, harvesting, custom.",
                status.HTTP_400_BAD_REQUEST,
                "category",
            )
        return text


class ActivityCycleListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_cycle_ref(cycle)
                for cycle in farm.crop_cycles.select_related(
                    "field", "crop"
                )
            ]
        )


class ActivityListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        activities = farm.activities.select_related(
            "cycle", "type"
        ).prefetch_related("input_needs")
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            activities = activities.filter(cycle_id=cycle_id)
        return Response(
            [serialize_activity(activity) for activity in activities]
        )

    def post(self, request):
        farm = get_farm(request.user)
        cycle = self._cycle(farm, request.data.get("cycleId"))
        activity_type = self._type(farm, request.data.get("typeId"))
        planned_date = parse_body_date(
            request.data,
            "plannedDate",
            "Planned date is required.",
            "Planned date must be a valid calendar date.",
        )
        activity = Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=planned_date,
            status=ActivityStatus.PLANNED,
            description=optional_text(request.data, "description"),
        )
        return Response(
            serialize_activity(activity), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _cycle(farm, cycle_id):
        if cycle_id in (None, ""):
            raise ApiError(
                "Select a crop cycle.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )
        try:
            return CropCycle.objects.get(farm=farm, pk=cycle_id)
        except (CropCycle.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected crop cycle does not exist.",
                status.HTTP_404_NOT_FOUND,
                "cycleId",
            )

    @staticmethod
    def _type(farm, type_id):
        if type_id in (None, ""):
            raise ApiError(
                "Select an activity type.",
                status.HTTP_400_BAD_REQUEST,
                "typeId",
            )
        try:
            return ActivityType.objects.get(farm=farm, pk=type_id)
        except (ActivityType.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected activity type does not exist.",
                status.HTTP_404_NOT_FOUND,
                "typeId",
            )


class ActivityDetailView(APIView):
    def put(self, request, activity_id):
        farm = get_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        cycle = ActivityListView._cycle(
            farm, request.data.get("cycleId")
        )
        activity_type = ActivityListView._type(
            farm, request.data.get("typeId")
        )
        planned_date = parse_body_date(
            request.data,
            "plannedDate",
            "Planned date is required.",
            "Planned date must be a valid calendar date.",
        )
        activity.cycle = cycle
        activity.type = activity_type
        activity.planned_date = planned_date
        activity.description = optional_text(
            request.data, "description"
        )
        activity.save()
        return Response(serialize_activity(activity))


class ActivityStatusView(APIView):
    def put(self, request, activity_id):
        farm = get_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        raw = request.data.get("status")
        target = str(raw).strip() if raw is not None else ""
        if target not in ActivityStatus.values:
            raise ApiError(
                "Status must be one of: planned, in progress, completed, "
                "overdue.",
                status.HTTP_400_BAD_REQUEST,
                "status",
            )
        if target not in ACTIVITY_TRANSITIONS[activity.status]:
            raise ApiError(
                f'Cannot move an activity from "'
                f'{self._label(activity.status)}" to "{target}".',
                status.HTTP_409_CONFLICT,
                "status",
            )
        activity.status = target
        activity.save(update_fields=["status"])
        return Response(serialize_activity(activity))

    @staticmethod
    def _label(value):
        return "in progress" if value == ActivityStatus.IN_PROGRESS else value


class ActivityResourceNeedsView(APIView):
    def put(self, request, activity_id):
        farm = get_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        data = request.data
        try:
            labour_hours = parse_decimal(
                data.get("labourHours"),
                "labourHours",
                "Labour hours are required.",
                "Labour hours must be a number.",
                negative_message="Labour hours cannot be negative.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "labourHours"
            )
        equipment = optional_text(data, "equipment")
        rows = data.get("inputs") or []
        if not isinstance(rows, list):
            raise ApiError(
                "Each input row needs an item name.",
                status.HTTP_400_BAD_REQUEST,
                "inputs",
            )
        needs = []
        for row in rows:
            if not isinstance(row, dict):
                raise ApiError(
                    "Each input row needs an item name.",
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                )
            item_name = str(row.get("itemName") or "").strip()
            if not item_name:
                raise ApiError(
                    "Each input row needs an item name.",
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                )
            try:
                quantity = parse_decimal(
                    row.get("quantity"),
                    "inputs",
                    "Quantity must be a number.",
                    "Quantity must be a number.",
                    positive_message="Quantity must be greater than zero.",
                )
            except ValueError as exc:
                raise ApiError(
                    str(exc), status.HTTP_400_BAD_REQUEST, "inputs"
                )
            needs.append((item_name, quantity))

        with transaction.atomic():
            activity.input_needs.all().delete()
            ActivityInputNeed.objects.bulk_create(
                [
                    ActivityInputNeed(
                        activity=activity,
                        item_name=item_name,
                        quantity=quantity,
                    )
                    for item_name, quantity in needs
                ]
            )
            activity.labour_hours = labour_hours
            activity.equipment = equipment
            activity.save(
                update_fields=["labour_hours", "equipment"]
            )

        return Response(serialize_activity(activity))


class InventoryItemListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_inventory_item(item)
                for item in farm.inventory_items.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        item = self._save(farm, None, request.data)
        return Response(
            serialize_inventory_item(item),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _save(farm, item, data):
        name = require_text(
            data, "name", "Inventory item name is required."
        )
        unit_id = data.get("unitId")
        if unit_id in (None, ""):
            raise ApiError(
                "Select a unit.", status.HTTP_400_BAD_REQUEST, "unitId"
            )
        try:
            unit = Unit.objects.get(farm=farm, pk=unit_id)
        except (Unit.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That unit does not exist.",
                status.HTTP_404_NOT_FOUND,
                "unitId",
            )
        reorder_level = parse_body_decimal(
            data,
            "reorderLevel",
            "Reorder level must be a number.",
            "Reorder level must be a number.",
            negative_message="Reorder level cannot be negative.",
        )
        if item is None:
            return InventoryItem.objects.create(
                farm=farm,
                name=name,
                unit=unit,
                reorder_level=reorder_level,
            )
        item.name = name
        item.unit = unit
        item.reorder_level = reorder_level
        item.save()
        return item


class InventoryItemDetailView(APIView):
    def put(self, request, item_id):
        farm = get_farm(request.user)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item no longer exists.",
        )
        item = InventoryItemListView._save(farm, item, request.data)
        return Response(serialize_inventory_item(item))


class ItemMovementListView(APIView):
    def get(self, request, item_id):
        farm = get_farm(request.user)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item no longer exists.",
        )
        return Response(
            [
                serialize_movement(movement)
                for movement in item.movements.all()
            ]
        )

    def post(self, request, item_id):
        farm = get_farm(request.user)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item does not exist.",
            "itemId",
        )
        body_item = request.data.get("itemId")
        if body_item in (None, ""):
            raise ApiError(
                "Select an inventory item.",
                status.HTTP_400_BAD_REQUEST,
                "itemId",
            )
        if str(body_item) != str(item.id):
            raise ApiError(
                "The itemId must match the path.",
                status.HTTP_400_BAD_REQUEST,
                "itemId",
            )
        movement_type = str(
            request.data.get("type") or ""
        ).strip()
        if movement_type not in MovementType.values:
            raise ApiError(
                "Movement type must be one of: purchase, usage, adjustment.",
                status.HTTP_400_BAD_REQUEST,
                "type",
            )
        try:
            quantity = parse_decimal(
                request.data.get("quantity"),
                "quantity",
                "Quantity must be a number.",
                "Quantity must be a number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
            )
        if movement_type == MovementType.ADJUSTMENT:
            if quantity == 0:
                raise ApiError(
                    "Adjustment quantity cannot be zero.",
                    status.HTTP_400_BAD_REQUEST,
                    "quantity",
                )
        elif quantity <= 0:
            raise ApiError(
                "Quantity must be a positive number.",
                status.HTTP_400_BAD_REQUEST,
                "quantity",
            )
        available = item.current_quantity()
        if (
            movement_type == MovementType.USAGE
            and quantity > available
        ):
            raise ApiError(
                f"Usage exceeds the available quantity "
                f"(available: {format_amount(available)}).",
                status.HTTP_400_BAD_REQUEST,
                "quantity",
            )
        movement_date = None
        if request.data.get("date") not in (None, ""):
            movement_date = parse_body_date(
                request.data,
                "date",
                "Date is required.",
                "Date must be a valid calendar date.",
            )
        movement = StockMovement.objects.create(
            farm=farm,
            item=item,
            type=movement_type,
            quantity=quantity,
            date=movement_date,
            note=optional_text(request.data, "note"),
        )
        return Response(
            serialize_movement(movement),
            status=status.HTTP_201_CREATED,
        )


class StockMovementListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_movement(movement)
                for movement in farm.stock_movements.all()
            ]
        )


class ExpenseListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_expense(expense)
                for expense in farm.expenses.prefetch_related(
                    "attachments"
                )
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        values = self._validate(request.data)
        expense = Expense.objects.create(
            farm=farm,
            category=values["category"],
            amount=values["amount"],
            date=values["date"],
            supplier=values["supplier"],
            status=ExpenseStatus.DRAFT,
        )
        return Response(
            serialize_expense(expense),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _validate(data):
        category = str(data.get("category") or "").strip()
        if category not in ExpenseCategory.values:
            raise ApiError(
                "Category must be one of: inputs, labour, equipment, "
                "overhead, other.",
                status.HTTP_400_BAD_REQUEST,
                "category",
            )
        try:
            amount = parse_decimal(
                data.get("amount"),
                "amount",
                "Amount is required.",
                "Amount must be a number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "amount"
            )
        try:
            expense_date = parse_date(
                data.get("date"),
                "date",
                "Date is required.",
                "Date must be a valid calendar date.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "date"
            )
        supplier = optional_text(data, "supplier")
        return {
            "category": category,
            "amount": amount,
            "date": expense_date,
            "supplier": supplier or None,
        }


class ExpenseDetailView(APIView):
    def put(self, request, expense_id):
        farm = get_farm(request.user)
        expense = scoped_get(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        if expense.status == ExpenseStatus.POSTED:
            raise ApiError(
                "Cannot edit a posted expense.",
                status.HTTP_400_BAD_REQUEST,
            )
        values = ExpenseListView._validate(request.data)
        expense.category = values["category"]
        expense.amount = values["amount"]
        expense.date = values["date"]
        expense.supplier = values["supplier"]
        expense.save()
        return Response(serialize_expense(expense))

    def delete(self, request, expense_id):
        farm = get_farm(request.user)
        expense = scoped_get(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        if expense.status == ExpenseStatus.POSTED:
            raise ApiError(
                "Cannot delete a posted expense.",
                status.HTTP_400_BAD_REQUEST,
            )
        expense.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExpensePostView(APIView):
    def post(self, request, expense_id):
        farm = get_farm(request.user)
        expense = scoped_get(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        if expense.status != ExpenseStatus.POSTED:
            expense.status = ExpenseStatus.POSTED
            expense.save(update_fields=["status"])
        return Response(serialize_expense(expense))


class ExpenseAttachmentView(APIView):
    def post(self, request, expense_id):
        farm = get_farm(request.user)
        expense = scoped_get(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        if expense.status == ExpenseStatus.POSTED:
            raise ApiError(
                "Posted expenses cannot be edited or deleted.",
                status.HTTP_400_BAD_REQUEST,
            )
        upload = request.FILES.get("file")
        if upload is None or not getattr(upload, "name", ""):
            raise ApiError(
                "Invalid attachment.", status.HTTP_400_BAD_REQUEST
            )
        attachment = Attachment.objects.create(
            expense=expense, file=upload, name=upload.name
        )
        return Response(
            serialize_attachment(attachment),
            status=status.HTTP_201_CREATED,
        )


class PaymentListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_payment(payment)
                for payment in farm.payments.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        payment_type = str(
            request.data.get("type") or ""
        ).strip()
        if payment_type not in PaymentType.values:
            raise ApiError(
                "Payment type must be either received or paid.",
                status.HTTP_400_BAD_REQUEST,
                "type",
            )
        try:
            amount = parse_decimal(
                request.data.get("amount"),
                "amount",
                "Amount is required.",
                "Amount must be a number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "amount"
            )
        try:
            payment_date = parse_date(
                request.data.get("date"),
                "date",
                "Date is required.",
                "Date must be a valid calendar date.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "date"
            )

        linked_expense = None
        expense_id = request.data.get("linkedExpenseId")
        if expense_id not in (None, ""):
            try:
                linked_expense = Expense.objects.get(
                    farm=farm, pk=expense_id
                )
            except (Expense.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "That expense no longer exists.",
                    status.HTTP_400_BAD_REQUEST,
                    "linkedExpenseId",
                )

        linked_sale = None
        sale_id = request.data.get("linkedSaleId")
        if sale_id not in (None, ""):
            try:
                linked_sale = Sale.objects.get(farm=farm, pk=sale_id)
            except (Sale.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "That sale no longer exists.",
                    status.HTTP_400_BAD_REQUEST,
                    "linkedSaleId",
                )

        reference = optional_text(request.data, "reference")
        payment = Payment.objects.create(
            farm=farm,
            type=payment_type,
            amount=amount,
            date=payment_date,
            linked_expense=linked_expense,
            linked_sale=linked_sale,
            reference=reference or None,
        )
        return Response(
            serialize_payment(payment),
            status=status.HTTP_201_CREATED,
        )


class HarvestCycleListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_cycle_ref(cycle)
                for cycle in farm.crop_cycles.select_related(
                    "field", "crop"
                )
            ]
        )


class HarvestCycleSummaryView(APIView):
    def get(self, request, cycle_id):
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        total, unit = aggregate_harvest_quantity_for_cycle(farm, cycle)
        return Response(
            {
                "cycleId": str(cycle.id),
                "totalHarvested": as_number(total),
                "unitId": str(unit.id) if unit is not None else None,
            }
        )


class HarvestDetailView(APIView):
    def get(self, request, harvest_id):
        farm = get_farm(request.user)
        harvest = scoped_get(
            Harvest, farm, harvest_id, "That harvest no longer exists."
        )
        return Response(serialize_harvest(harvest))

    def patch(self, request, harvest_id):
        farm = get_farm(request.user)
        harvest = scoped_get(
            Harvest, farm, harvest_id, "That harvest no longer exists."
        )
        if harvest.cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be harvested.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )

        data = request.data
        if "cycleId" in data:
            cycle_id = data.get("cycleId")
            if cycle_id in (None, ""):
                raise ApiError(
                    "Select a crop cycle.",
                    status.HTTP_400_BAD_REQUEST,
                    "cycleId",
                )
            try:
                cycle = CropCycle.objects.get(farm=farm, pk=cycle_id)
            except (CropCycle.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "That crop cycle no longer exists.",
                    status.HTTP_404_NOT_FOUND,
                    "cycleId",
                )
            if cycle.status == CycleStatus.CLOSED:
                raise ApiError(
                    "This crop cycle is closed and can no longer be harvested.",
                    status.HTTP_400_BAD_REQUEST,
                    "cycleId",
                )
            harvest.cycle = cycle

        if "quantity" in data:
            try:
                quantity = parse_decimal(
                    data.get("quantity"),
                    "quantity",
                    "Quantity is required.",
                    "Quantity must be a number.",
                    positive_message="Quantity must be greater than zero.",
                )
            except ValueError as exc:
                raise ApiError(
                    str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
                )
            harvest.quantity = quantity

        if "unitId" in data:
            unit_id = data.get("unitId")
            if unit_id in (None, ""):
                raise ApiError(
                    "Select a unit.",
                    status.HTTP_400_BAD_REQUEST,
                    "unitId",
                )
            try:
                unit = Unit.objects.get(farm=farm, pk=unit_id)
            except (Unit.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "That unit does not exist.",
                    status.HTTP_400_BAD_REQUEST,
                    "unitId",
                )
            harvest.unit = unit

        if "date" in data:
            harvest_date = parse_body_date(
                data,
                "date",
                "Date is required.",
                "Date must be a valid calendar date.",
            )
            harvest.date = harvest_date

        harvest.save()
        return Response(serialize_harvest(harvest))

    def put(self, request, harvest_id):
        return self.patch(request, harvest_id)

    def delete(self, request, harvest_id):
        farm = get_farm(request.user)
        harvest = scoped_get(
            Harvest, farm, harvest_id, "That harvest no longer exists."
        )
        if harvest.cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be harvested.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )
        harvest.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _convert_quantity_between_units(farm, quantity, from_unit, to_unit):
    if from_unit.pk == to_unit.pk:
        return quantity
    if from_unit.base_measure != to_unit.base_measure:
        raise ApiError(
            f'Cannot convert "{from_unit.name}" '
            f"({from_unit.base_measure}) to \"{to_unit.name}\" "
            f"({to_unit.base_measure}): base measures do not match.",
            status.HTTP_400_BAD_REQUEST,
        )

    forward = UnitConversion.objects.filter(
        farm=farm, from_unit=from_unit, to_unit=to_unit
    ).first()
    if forward is not None:
        return quantity * forward.factor

    reverse = UnitConversion.objects.filter(
        farm=farm, from_unit=to_unit, to_unit=from_unit
    ).first()
    if reverse is None:
        raise ApiError(
            f'No rule exists for converting from '
            f'"{from_unit.name}" to "{to_unit.name}".',
            status.HTTP_400_BAD_REQUEST,
        )
    return quantity / reverse.factor


def aggregate_harvest_quantity_for_cycle(farm, cycle):
    harvests = list(
        Harvest.objects.filter(farm=farm, cycle=cycle).select_related(
            "unit"
        )
    )
    if not harvests:
        return Decimal(0), None

    target_unit = harvests[0].unit
    total = Decimal(0)
    for harvest in harvests:
        converted = _convert_quantity_between_units(
            farm, harvest.quantity, harvest.unit, target_unit
        )
        total += converted
    return total, target_unit


class HarvestListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        harvests = farm.harvests.all()
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            harvests = harvests.filter(cycle_id=cycle_id)
        return Response(
            [serialize_harvest(harvest) for harvest in harvests]
        )

    def post(self, request):
        farm = get_farm(request.user)
        cycle_id = request.data.get("cycleId")
        if cycle_id in (None, ""):
            raise ApiError(
                "Select a crop cycle.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )
        try:
            cycle = CropCycle.objects.get(farm=farm, pk=cycle_id)
        except (CropCycle.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That crop cycle no longer exists.",
                status.HTTP_404_NOT_FOUND,
                "cycleId",
            )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be harvested.",
                status.HTTP_400_BAD_REQUEST,
                "cycleId",
            )
        try:
            quantity = parse_decimal(
                request.data.get("quantity"),
                "quantity",
                "Quantity is required.",
                "Quantity must be a number.",
                positive_message="Quantity must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
            )
        unit_id = request.data.get("unitId")
        if unit_id in (None, ""):
            raise ApiError(
                "Select a unit.",
                status.HTTP_400_BAD_REQUEST,
                "unitId",
            )
        try:
            unit = Unit.objects.get(farm=farm, pk=unit_id)
        except (Unit.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That unit does not exist.",
                status.HTTP_400_BAD_REQUEST,
                "unitId",
            )
        harvest_date = parse_body_date(
            request.data,
            "date",
            "Date is required.",
            "Date must be a valid calendar date.",
        )
        harvest = Harvest.objects.create(
            farm=farm,
            cycle=cycle,
            quantity=quantity,
            unit=unit,
            date=harvest_date,
        )
        return Response(
            serialize_harvest(harvest),
            status=status.HTTP_201_CREATED,
        )


class CustomerListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_customer(customer)
                for customer in farm.customers.all()
            ]
        )


class SaleListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_sale(sale) for sale in farm.sales.all()]
        )

    def post(self, request):
        farm = get_farm(request.user)
        customer_id = request.data.get("customerId")
        if customer_id in (None, ""):
            raise ApiError(
                "Select a customer.",
                status.HTTP_400_BAD_REQUEST,
                "customerId",
            )
        try:
            customer = Customer.objects.get(
                farm=farm, pk=customer_id
            )
        except (Customer.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That customer does not exist.",
                status.HTTP_400_BAD_REQUEST,
                "customerId",
            )

        harvest_id = request.data.get("harvestId")
        if harvest_id in (None, ""):
            raise ApiError(
                "Select a harvest.",
                status.HTTP_400_BAD_REQUEST,
                "harvestId",
            )
        try:
            harvest = Harvest.objects.get(farm=farm, pk=harvest_id)
        except (Harvest.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That harvest no longer exists.",
                status.HTTP_400_BAD_REQUEST,
                "harvestId",
            )

        try:
            quantity = parse_decimal(
                request.data.get("quantity"),
                "quantity",
                "Quantity is required.",
                "Quantity must be a number.",
                positive_message="Quantity must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
            )
        try:
            unit_price = parse_decimal(
                request.data.get("unitPrice"),
                "unitPrice",
                "Unit price is required.",
                "Unit price must be a number.",
                positive_message="Unit price must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "unitPrice"
            )
        sale_date = parse_body_date(
            request.data,
            "date",
            "Date is required.",
            "Date must be a valid calendar date.",
        )

        sold = sum(
            (
                sale.quantity
                for sale in harvest.sales.all()
            ),
            Decimal(0),
        )
        available = harvest.quantity - sold
        if quantity > available:
            raise ApiError(
                "Sold quantity exceeds the harvested quantity available. "
                f"Maximum sellable is {format_amount(available)}.",
                status.HTTP_400_BAD_REQUEST,
                "quantity",
            )

        revenue = (quantity * unit_price).quantize(Decimal("0.0001"))
        sale = Sale.objects.create(
            farm=farm,
            customer=customer,
            harvest=harvest,
            quantity=quantity,
            unit_price=unit_price,
            date=sale_date,
            revenue=revenue,
        )
        return Response(
            serialize_sale(sale), status=status.HTTP_201_CREATED
        )


class SaleDetailView(APIView):
    def get(self, request, sale_id):
        farm = get_farm(request.user)
        sale = scoped_get(
            Sale, farm, sale_id, "That sale no longer exists."
        )
        return Response(serialize_sale(sale))

    def delete(self, request, sale_id):
        farm = get_farm(request.user)
        sale = scoped_get(
            Sale, farm, sale_id, "That sale no longer exists."
        )
        sale.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
