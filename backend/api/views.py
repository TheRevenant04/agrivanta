from decimal import Decimal
from uuid import UUID

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView as RestFrameworkAPIView

from .audit import AuditedAPIViewMixin, actor_context
from .exceptions import ApiError
from .import_service import (
    SUPPORTED_ENTITY_TYPES,
    ImportCommitError,
    ImportFileError,
    commit_import,
    preview_import,
)
from .models import (
    AuditEvent,
    Activity,
    ActivityCategory,
    ActivityInputNeed,
    ActivityStatus,
    ActivityType,
    BaseMeasure,
    Budget,
    Crop,
    CropCycle,
    CycleStatus,
    CycleType,
    Customer,
    Expense,
    ExpenseCategory,
    ExpenseCategoryRecord,
    ExpenseStatus,
    Equipment,
    EquipmentUsage,
    ensure_default_expense_categories,
    Farm,
    Field,
    Harvest,
    InventoryItem,
    LabourRecord,
    MovementType,
    Notification,
    Payment,
    PaymentType,
    PlannedEquipment,
    PlannedInput,
    PlannedLabour,
    RecurringExpenseFrequency,
    RecurringExpenseTemplate,
    ReportingPeriod,
    Role,
    Sale,
    Season,
    Supplier,
    StockMovement,
    Supplier,
    Unit,
    UnitConversion,
    User,
    Variety,
    Worker,
)
from .report_exports import render_report_export, report_payload
from .serializers import (
    as_date,
    as_number,
    cycle_label,
    parse_date,
    parse_decimal,
    serialize_activity,
    serialize_activity_type,
    serialize_budget,
    serialize_conversion,
    serialize_crop,
    serialize_cycle,
    serialize_cycle_ref,
    serialize_customer,
    serialize_expense,
    serialize_equipment,
    serialize_equipment_usage,
    serialize_expense_category,
    serialize_farm,
    serialize_field,
    serialize_harvest,
    serialize_inventory_item,
    serialize_labour_record,
    serialize_movement,
    serialize_notification,
    serialize_payment,
    serialize_recurring_expense_template,
    serialize_reporting_period,
    serialize_sale,
    serialize_season,
    serialize_supplier,
    serialize_unit,
    serialize_user,
    serialize_variety,
    serialize_worker,
)
from .transactions import ReversalError, reverse_expense, reverse_payment
from .unit_conversion import (
    ConversionRuleData,
    MissingConversionRuleError,
    UnitConversionError,
    UnitData,
    conversion_factor,
    convert_quantity,
)

STANDARD_ACTIVITY_TEMPLATES = (
    ("Land preparation", ActivityCategory.LAND_PREPARATION),
    ("Planting", ActivityCategory.PLANTING),
    ("Fertilizing", ActivityCategory.FERTILIZING),
    ("Spraying", ActivityCategory.SPRAYING),
    ("Harvesting", ActivityCategory.HARVESTING),
)


class APIView(AuditedAPIViewMixin, RestFrameworkAPIView):
    pass

DEFAULT_CUSTOMER_NAMES = ["Greenfield Grain Co.", "Harbour Mill"]

COUNTERPARTY_OPTIONAL_FIELDS = (
    ("contactName", "contact_name"),
    ("email", "email"),
    ("phone", "phone"),
    ("address", "address"),
    ("notes", "notes"),
)
COUNTERPARTY_MAX_LENGTHS = {
    api_field: Supplier._meta.get_field(model_field).max_length
    for api_field, model_field in COUNTERPARTY_OPTIONAL_FIELDS
}

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


def require_name(data, key, noun):
    name = require_text(data, key, f"{noun} name is required.")
    if len(name) > 255:
        raise ApiError(
            f"{noun.capitalize()} name must be 255 characters or fewer.",
            status.HTTP_400_BAD_REQUEST,
            key,
        )
    return name


def ensure_unique_farm_name(model, farm, name, noun, instance=None):
    matches = model.objects.filter(farm=farm, name__iexact=name)
    if instance is not None:
        matches = matches.exclude(pk=instance.pk)
    if matches.exists():
        raise ApiError(
            f'A {noun.lower()} named "{name}" already exists.',
            status.HTTP_409_CONFLICT,
            "name",
        )


def save_unique_farm_name(instance, noun):
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError:
        raise ApiError(
            f'A {noun.lower()} named "{instance.name}" already exists.',
            status.HTTP_409_CONFLICT,
            "name",
        )


def optional_text(data, key):
    value = data.get(key)
    if value is None:
        return ""
    return str(value).strip()


def validate_counterparty_length(value, api_field):
    max_length = COUNTERPARTY_MAX_LENGTHS[api_field]
    if max_length and len(value) > max_length:
        raise ApiError(
            f"Ensure this field has no more than {max_length} characters.",
            status.HTTP_400_BAD_REQUEST,
            api_field,
        )
    return value


def get_farm(user):
    farm = getattr(user, "farm", None)
    if farm is None:
        raise ApiError(
            "No farm is configured.", status.HTTP_404_NOT_FOUND
        )
    return farm


def get_activity_farm(user):
    if user.role == Role.MANAGER:
        memberships = user.member_farms.all()
        if memberships.count() == 1:
            return memberships.first()
    return get_farm(user)


def get_inventory_farm(request):
    require_activity_manager(request)
    return get_activity_farm(request.user)


def require_activity_manager(request):
    if request.user.role not in (Role.OWNER, Role.MANAGER):
        raise ApiError(
            "Only farm owners and managers can manage activities.",
            status.HTTP_403_FORBIDDEN,
        )


def activity_queryset_for(request):
    if request.user.role == Role.WORKER:
        return (
            Activity.objects.filter(assignees=request.user)
            .filter(
                Q(farm__owner=request.user)
                | Q(farm__members=request.user)
            )
            .distinct()
        )
    farm = get_activity_farm(request.user)
    return farm.activities.all()


def get_visible_activity(request, activity_id):
    try:
        return activity_queryset_for(request).get(pk=activity_id)
    except (Activity.DoesNotExist, ValueError, ValidationError):
        raise ApiError(
            "That activity no longer exists.", status.HTTP_404_NOT_FOUND
        )


def ensure_activity_cycle_open(activity):
    if activity.cycle.status == CycleStatus.CLOSED:
        raise ApiError(
            "Activities in a closed crop cycle cannot be changed.",
            status.HTTP_409_CONFLICT,
        )


def require_farm_setup_write(request):
    if request.user.role not in (Role.OWNER, Role.MANAGER):
        raise ApiError(
            "Only farm owners and managers can change setup records.",
            status.HTTP_403_FORBIDDEN,
        )


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


def parse_field_area(data):
    area = parse_body_decimal(
        data,
        "area",
        "Area is required.",
        "Area must be a number.",
        positive_message="Area must be greater than zero.",
    )
    try:
        Field._meta.get_field("area").run_validators(area)
    except ValidationError as exc:
        raise ApiError(
            "Area must fit within 10 integer digits and 4 decimal places.",
            status.HTTP_400_BAD_REQUEST,
            "area",
        ) from exc
    return area


def parse_field_polygon(value):
    if value is None:
        return None

    def invalid():
        raise ApiError(
            "Polygon must be a valid GeoJSON Polygon.",
            status.HTTP_400_BAD_REQUEST,
            "polygon",
        )

    if not isinstance(value, dict) or value.get("type") != "Polygon":
        invalid()
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        invalid()

    position_dimensions = None
    for ring in coordinates:
        if not isinstance(ring, list) or len(ring) < 4:
            invalid()
        dimensions = None
        for position in ring:
            if not isinstance(position, list) or len(position) < 2:
                invalid()
            if dimensions is None:
                dimensions = len(position)
            if len(position) != dimensions:
                invalid()
            for coordinate in position:
                if isinstance(coordinate, bool) or not isinstance(
                    coordinate, (int, float)
                ):
                    invalid()
                try:
                    number = Decimal(str(coordinate))
                except (ArithmeticError, ValueError):
                    invalid()
                if not number.is_finite():
                    invalid()
            if position_dimensions is None:
                position_dimensions = dimensions
            elif dimensions != position_dimensions:
                invalid()
        if ring[0] != ring[-1]:
            invalid()
    return value


def parse_optional_body_date(data, key, invalid_message):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        return parse_date(value, key, invalid_message, invalid_message)
    except ValueError as exc:
        raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST, key)


def create_farm_for(request):
    farm_id = request.data.get("farmId")
    if farm_id in (None, ""):
        return get_farm(request.user)
    try:
        farm = Farm.objects.get(pk=farm_id)
    except (Farm.DoesNotExist, ValueError, ValidationError):
        raise ApiError(
            "The selected farm does not exist.",
            status.HTTP_400_BAD_REQUEST,
            "farmId",
        )
    if farm.owner_id != request.user.id:
        raise ApiError(
            "You do not have access to that farm.",
            status.HTTP_403_FORBIDDEN,
            "farmId",
        )
    return farm


def parse_optional_year(data):
    value = data.get("year")
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        raise ApiError(
            "Year must be a whole number.",
            status.HTTP_400_BAD_REQUEST,
            "year",
        )
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ApiError(
            "Year must be a whole number.",
            status.HTTP_400_BAD_REQUEST,
            "year",
        )


def parse_period_payload(data, noun):
    name = require_text(data, "name", f"{noun.capitalize()} name is required.")
    start_date = parse_body_date(
        data,
        "startDate",
        "Start date is required.",
        "Start date must be a valid calendar date.",
    )
    end_date = parse_body_date(
        data,
        "endDate",
        "End date is required.",
        "End date must be a valid calendar date.",
    )
    if end_date < start_date:
        raise ApiError(
            "End date cannot be before the start date.",
            status.HTTP_400_BAD_REQUEST,
            "endDate",
        )
    return {
        "name": name,
        "start_date": start_date,
        "end_date": end_date,
        "year": parse_optional_year(data),
    }


def ensure_unique_period_name(model, farm, name, noun, instance=None):
    query = model.objects.filter(farm=farm, name__iexact=name)
    if instance is not None:
        query = query.exclude(pk=instance.pk)
    if query.exists():
        raise ApiError(
            f'A {noun} named "{name}" already exists.',
            status.HTTP_400_BAD_REQUEST,
            "name",
        )


def seed_farm(farm):
    for name, category in STANDARD_ACTIVITY_TEMPLATES:
        ActivityType.objects.get_or_create(
            farm=farm,
            name=name,
            defaults={"category": category, "standard": True},
        )
    for name in DEFAULT_CUSTOMER_NAMES:
        Customer.objects.get_or_create(farm=farm, name=name)


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
                status.HTTP_400_BAD_REQUEST,
                "email",
            )

        name = str(data.get("name") or "").strip()
        farm_name = f"{name}'s Farm" if name else "My Farm"
        if len(farm_name) > 255:
            raise ApiError(
                "Farm name must be 255 characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
                "name",
            )
        try:
            validate_password(password, user=User(email=email, name=name))
        except ValidationError as exc:
            raise ApiError(
                " ".join(exc.messages),
                status.HTTP_400_BAD_REQUEST,
                "password",
            )

        with transaction.atomic():
            user = User.objects.create_user(
                email=email, password=password, name=name
            )
            with actor_context(user):
                farm = Farm.objects.create(
                    owner=user,
                    name=farm_name,
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


def parse_reporting_currency(value):
    if (
        not isinstance(value, str)
        or len(value.strip()) != 3
        or not value.strip().isascii()
        or not value.strip().isalpha()
    ):
        raise ApiError(
            "Reporting currency must be a three-letter code such as USD.",
            status.HTTP_400_BAD_REQUEST,
            "reportingCurrency",
        )
    return value.strip()


class FarmView(APIView):
    def get(self, request):
        return Response(serialize_farm(get_farm(request.user)))

    def put(self, request):
        farm = get_farm(request.user)
        name = require_name(request.data, "name", "Farm")
        currency = parse_reporting_currency(
            request.data.get("reportingCurrency")
        )
        farm.name = name
        farm.reporting_currency = currency.upper()
        farm.save(update_fields=["name", "reporting_currency"])
        return Response(serialize_farm(farm))

    def patch(self, request):
        farm = get_farm(request.user)
        update_fields = []
        if "name" in request.data:
            farm.name = require_name(request.data, "name", "Farm")
            update_fields.append("name")
        if "reportingCurrency" in request.data:
            currency = parse_reporting_currency(
                request.data["reportingCurrency"]
            )
            farm.reporting_currency = currency.upper()
            update_fields.append("reporting_currency")
        if update_fields:
            farm.save(update_fields=update_fields)
        return Response(serialize_farm(farm))


class FarmSetupStatusView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        steps = {
            "farm": bool(farm.name.strip() and len(farm.reporting_currency) == 3),
            "fields": farm.fields.exists(),
            "crops": farm.crops.filter(varieties__farm=farm).exists(),
            "initialCycle": farm.crop_cycles.exists(),
        }
        next_step = next(
            (step for step, complete in steps.items() if not complete), None
        )
        return Response(
            {
                "steps": steps,
                "complete": next_step is None,
                "nextStep": next_step,
            }
        )


class AuditEventListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == Role.OWNER:
            farm = Farm.objects.filter(owner=user).first()
        elif user.role == Role.MANAGER:
            memberships = user.member_farms.all()
            farm = memberships.first() if memberships.count() == 1 else None
        else:
            farm = None
        if farm is None:
            raise ApiError(
                "You are not authorized to view this farm's audit history.",
                status.HTTP_403_FORBIDDEN,
            )

        model_name = str(request.query_params.get("model", "")).lower()
        model_names = {
            "farm": "Farm",
            "cropcycle": "CropCycle",
            "expense": "Expense",
            "inventoryitem": "InventoryItem",
            "stockmovement": "StockMovement",
        }
        record_id = str(request.query_params.get("recordId", "")).strip()
        if model_name not in model_names or not record_id:
            raise ApiError(
                "A valid model and recordId are required.",
                status.HTTP_400_BAD_REQUEST,
            )

        events = AuditEvent.objects.filter(
            farm_id=farm.pk,
            model=model_names[model_name],
            record_id=record_id,
        )
        return Response(
            [
                {
                    "id": str(event.pk),
                    "model": event.model,
                    "recordId": event.record_id,
                    "action": event.action,
                    "changes": event.changes,
                    "actor": {
                        "type": event.actor_type,
                        "id": event.actor_id,
                        "name": event.actor_name,
                    },
                    "timestamp": event.timestamp.isoformat(),
                    "relatedRecordId": event.related_record_id or None,
                    "relatedEventId": (
                        str(event.related_event_id)
                        if event.related_event_id
                        else None
                    ),
                }
                for event in events
            ]
        )


class PeriodListView(APIView):
    model = None
    noun = None
    serializer = None

    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                self.serializer(period)
                for period in self.model.objects.filter(farm=farm)
            ]
        )

    def post(self, request):
        farm = create_farm_for(request)
        values = parse_period_payload(request.data, self.noun)
        ensure_unique_period_name(
            self.model, farm, values["name"], self.noun
        )
        period = self.model.objects.create(farm=farm, **values)
        return Response(
            self.serializer(period), status=status.HTTP_201_CREATED
        )


class PeriodDetailView(APIView):
    model = None
    noun = None
    serializer = None
    missing_message = None
    pk_kwarg = "period_id"

    def _object(self, farm, kwargs):
        return scoped_get(
            self.model,
            farm,
            kwargs[self.pk_kwarg],
            self.missing_message,
        )

    def get(self, request, **kwargs):
        farm = get_farm(request.user)
        period = self._object(farm, kwargs)
        return Response(self.serializer(period))

    def put(self, request, **kwargs):
        farm = get_farm(request.user)
        period = self._object(farm, kwargs)
        values = parse_period_payload(request.data, self.noun)
        ensure_unique_period_name(
            self.model,
            farm,
            values["name"],
            self.noun,
            instance=period,
        )
        period.name = values["name"]
        period.start_date = values["start_date"]
        period.end_date = values["end_date"]
        period.year = values["year"]
        period.save()
        return Response(self.serializer(period))

    def delete(self, request, **kwargs):
        farm = get_farm(request.user)
        period = self._object(farm, kwargs)
        period.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SeasonListView(PeriodListView):
    model = Season
    noun = "season"
    serializer = staticmethod(serialize_season)


class SeasonDetailView(PeriodDetailView):
    model = Season
    noun = "season"
    serializer = staticmethod(serialize_season)
    missing_message = "That season no longer exists."
    pk_kwarg = "season_id"


class ReportingPeriodListView(PeriodListView):
    model = ReportingPeriod
    noun = "reporting period"
    serializer = staticmethod(serialize_reporting_period)


class ReportingPeriodDetailView(PeriodDetailView):
    model = ReportingPeriod
    noun = "reporting period"
    serializer = staticmethod(serialize_reporting_period)
    missing_message = "That reporting period no longer exists."
    pk_kwarg = "period_id"


class FieldListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_field(field) for field in farm.fields.all()]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_name(request.data, "name", "Field")
        area = parse_field_area(request.data)
        polygon = parse_field_polygon(request.data.get("polygon"))
        field = Field.objects.create(
            farm=farm,
            name=name,
            area=area,
            notes=optional_text(request.data, "notes"),
            polygon=polygon,
        )
        return Response(
            serialize_field(field), status=status.HTTP_201_CREATED
        )


class FieldDetailView(APIView):
    def get(self, request, field_id):
        farm = get_farm(request.user)
        field = scoped_get(
            Field, farm, field_id, "That field no longer exists."
        )
        return Response(serialize_field(field))

    def put(self, request, field_id):
        farm = get_farm(request.user)
        field = scoped_get(
            Field, farm, field_id, "That field no longer exists."
        )
        name = require_name(request.data, "name", "Field")
        area = parse_field_area(request.data)
        field.name = name
        field.area = area
        field.notes = optional_text(request.data, "notes")
        field.polygon = parse_field_polygon(request.data.get("polygon"))
        field.save()
        return Response(serialize_field(field))

    def patch(self, request, field_id):
        farm = get_farm(request.user)
        field = scoped_get(
            Field, farm, field_id, "That field no longer exists."
        )
        update_fields = []
        if "name" in request.data:
            field.name = require_name(request.data, "name", "Field")
            update_fields.append("name")
        if "area" in request.data:
            field.area = parse_field_area(request.data)
            update_fields.append("area")
        if "notes" in request.data:
            field.notes = optional_text(request.data, "notes")
            update_fields.append("notes")
        if "polygon" in request.data:
            field.polygon = parse_field_polygon(request.data["polygon"])
            update_fields.append("polygon")
        if update_fields:
            field.save(update_fields=update_fields + ["updated_at"])
        return Response(serialize_field(field))

    def delete(self, request, field_id):
        farm = get_farm(request.user)
        field = scoped_get(
            Field, farm, field_id, "That field no longer exists."
        )
        field.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CropListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_crop(crop) for crop in farm.crops.all()]
        )

    def post(self, request):
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        name = require_name(request.data, "name", "Crop")
        ensure_unique_farm_name(Crop, farm, name, "Crop")
        crop = Crop(farm=farm, name=name)
        save_unique_farm_name(crop, "Crop")
        return Response(
            serialize_crop(crop), status=status.HTTP_201_CREATED
        )


class CropDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, crop_id):
        farm = get_farm(request.user)
        crop = scoped_get(
            Crop, farm, crop_id, "That crop no longer exists."
        )
        return Response(serialize_crop(crop))

    def put(self, request, crop_id):
        farm = get_farm(request.user)
        crop = scoped_get(
            Crop, farm, crop_id, "That crop no longer exists."
        )
        require_farm_setup_write(request)
        name = require_name(request.data, "name", "Crop")
        ensure_unique_farm_name(Crop, farm, name, "Crop", crop)
        crop.name = name
        save_unique_farm_name(crop, "Crop")
        return Response(serialize_crop(crop))

    def patch(self, request, crop_id):
        farm = get_farm(request.user)
        crop = scoped_get(
            Crop, farm, crop_id, "That crop no longer exists."
        )
        require_farm_setup_write(request)
        if "name" in request.data:
            crop.name = require_name(request.data, "name", "Crop")
            ensure_unique_farm_name(Crop, farm, crop.name, "Crop", crop)
            save_unique_farm_name(crop, "Crop")
        return Response(serialize_crop(crop))

    def delete(self, request, crop_id):
        farm = get_farm(request.user)
        crop = scoped_get(
            Crop, farm, crop_id, "That crop no longer exists."
        )
        require_farm_setup_write(request)
        if crop.crop_cycles.exists() or crop.varieties.filter(
            crop_cycles__isnull=False
        ).exists():
            raise ApiError(
                "A crop referenced by a crop cycle cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        try:
            crop.delete()
        except (ProtectedError, RestrictedError):
            raise ApiError(
                "A crop referenced by a crop cycle cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class VarietyListView(APIView):
    permission_classes = (IsAuthenticated,)

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
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        crop = self._crop(farm, request.data.get("cropId"))
        name = require_name(request.data, "name", "Variety")
        variety = Variety(farm=farm, crop=crop, name=name)
        variety.save()
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
    permission_classes = (IsAuthenticated,)

    def get(self, request, variety_id):
        farm = get_farm(request.user)
        variety = scoped_get(
            Variety, farm, variety_id, "That variety no longer exists."
        )
        return Response(serialize_variety(variety))

    def put(self, request, variety_id):
        farm = get_farm(request.user)
        variety = scoped_get(
            Variety, farm, variety_id, "That variety no longer exists."
        )
        require_farm_setup_write(request)
        crop = VarietyListView._crop(farm, request.data.get("cropId"))
        name = require_name(request.data, "name", "Variety")
        variety.crop = crop
        variety.name = name
        variety.save(update_fields=["crop", "name"])
        return Response(serialize_variety(variety))

    def patch(self, request, variety_id):
        farm = get_farm(request.user)
        variety = scoped_get(
            Variety, farm, variety_id, "That variety no longer exists."
        )
        require_farm_setup_write(request)
        update_fields = []
        if "cropId" in request.data:
            variety.crop = VarietyListView._crop(
                farm, request.data.get("cropId")
            )
            update_fields.append("crop")
        if "name" in request.data:
            variety.name = require_name(request.data, "name", "Variety")
            update_fields.append("name")
        if update_fields:
            variety.save(update_fields=update_fields + ["updated_at"])
        return Response(serialize_variety(variety))

    def delete(self, request, variety_id):
        farm = get_farm(request.user)
        variety = scoped_get(
            Variety, farm, variety_id, "That variety no longer exists."
        )
        require_farm_setup_write(request)
        if variety.crop_cycles.exists():
            raise ApiError(
                "A variety referenced by a crop cycle cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        try:
            variety.delete()
        except (ProtectedError, RestrictedError):
            raise ApiError(
                "A variety referenced by a crop cycle cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnitListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [serialize_unit(unit) for unit in farm.units.all()]
        )

    def post(self, request):
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        name = require_name(request.data, "name", "Unit")
        base_measure = self._base_measure(request.data.get("baseMeasure"))
        ensure_unique_farm_name(Unit, farm, name, "Unit")
        unit = Unit(farm=farm, name=name, base_measure=base_measure)
        save_unique_farm_name(unit, "Unit")
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
    permission_classes = (IsAuthenticated,)

    def get(self, request, unit_id):
        farm = get_farm(request.user)
        unit = scoped_get(
            Unit, farm, unit_id, "That unit no longer exists."
        )
        return Response(serialize_unit(unit))

    def put(self, request, unit_id):
        farm = get_farm(request.user)
        unit = scoped_get(
            Unit, farm, unit_id, "That unit no longer exists."
        )
        require_farm_setup_write(request)
        name = require_name(request.data, "name", "Unit")
        base_measure = UnitListView._base_measure(
            request.data.get("baseMeasure")
        )
        ensure_unique_farm_name(Unit, farm, name, "Unit", unit)
        unit.name = name
        unit.base_measure = base_measure
        save_unique_farm_name(unit, "Unit")
        return Response(serialize_unit(unit))

    def patch(self, request, unit_id):
        farm = get_farm(request.user)
        unit = scoped_get(
            Unit, farm, unit_id, "That unit no longer exists."
        )
        require_farm_setup_write(request)
        if "name" in request.data:
            unit.name = require_name(request.data, "name", "Unit")
            ensure_unique_farm_name(Unit, farm, unit.name, "Unit", unit)
        if "baseMeasure" in request.data:
            unit.base_measure = UnitListView._base_measure(
                request.data.get("baseMeasure")
            )
        if "name" in request.data or "baseMeasure" in request.data:
            save_unique_farm_name(unit, "Unit")
        return Response(serialize_unit(unit))

    def delete(self, request, unit_id):
        farm = get_farm(request.user)
        unit = scoped_get(
            Unit, farm, unit_id, "That unit no longer exists."
        )
        require_farm_setup_write(request)
        if unit.inventory_items.exists() or unit.harvests.exists():
            raise ApiError(
                "A unit referenced by inventory or harvest records cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        try:
            unit.delete()
        except (ProtectedError, RestrictedError):
            raise ApiError(
                "A unit referenced by inventory or harvest records cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


def unit_lookup(farm, unit_id, field):
    if unit_id in (None, ""):
        raise ApiError(
            "Select a unit.", status.HTTP_400_BAD_REQUEST, field
        )
    try:
        return Unit.objects.get(farm=farm, pk=unit_id)
    except (Unit.DoesNotExist, TypeError, ValueError, ValidationError):
        raise ApiError(
            "That unit does not exist.",
            status.HTTP_404_NOT_FOUND,
            field,
        )


def validate_conversion_rule(
    farm,
    from_unit,
    to_unit,
    *,
    existing_instance=None,
):
    if from_unit.pk == to_unit.pk:
        raise ApiError(
            "Choose two different units.",
            status.HTTP_400_BAD_REQUEST,
            "toUnitId",
        )
    if from_unit.base_measure != to_unit.base_measure:
        raise ApiError(
            "Units must share the same base measure category.",
            status.HTTP_400_BAD_REQUEST,
            "toUnitId",
        )
    if conversion_pair_query(
        farm, from_unit, to_unit, existing_instance=existing_instance
    ).exists():
        raise_conversion_pair_conflict(from_unit, to_unit)


def raise_conversion_pair_conflict(from_unit, to_unit):
    raise ApiError(
        f'A conversion rule for "{from_unit.name}" and '
        f'"{to_unit.name}" already exists.',
        status.HTTP_409_CONFLICT,
        "toUnitId",
    )


def conversion_pair_query(farm, from_unit, to_unit, existing_instance=None):
    query = UnitConversion.objects.filter(farm=farm).filter(
        Q(from_unit=from_unit, to_unit=to_unit)
        | Q(from_unit=to_unit, to_unit=from_unit)
    )
    if existing_instance is not None:
        query = query.exclude(pk=existing_instance.pk)
    return query


def lock_conversion_farm(farm):
    Farm.objects.select_for_update().get(pk=farm.pk)


def parse_conversion_factor(value):
    try:
        factor = parse_decimal(
            value,
            "factor",
            "Conversion factor must be a positive number.",
            "Conversion factor must be a positive number.",
            positive_message="Conversion factor must be a positive number.",
        )
    except ValueError as exc:
        raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST, "factor")
    try:
        return UnitConversion._meta.get_field("factor").clean(factor, None)
    except ValidationError as exc:
        raise ApiError(
            "Conversion factor must fit within 18 digits and 6 decimal places.",
            status.HTTP_400_BAD_REQUEST,
            "factor",
        ) from exc


def save_conversion_rule(
    conversion,
    farm,
    from_unit,
    to_unit,
    factor_value,
    *,
    existing_instance=None,
    update_fields=None,
):
    with transaction.atomic():
        lock_conversion_farm(farm)
        validate_conversion_rule(
            farm,
            from_unit,
            to_unit,
            existing_instance=existing_instance,
        )
        factor = parse_conversion_factor(factor_value)
        conversion.from_unit = from_unit
        conversion.to_unit = to_unit
        conversion.factor = factor
        conversion.save(update_fields=update_fields)


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
        conversion = UnitConversion(
            farm=farm,
            from_unit=from_unit,
            to_unit=to_unit,
        )
        save_conversion_rule(
            conversion,
            farm,
            from_unit,
            to_unit,
            request.data.get("factor"),
        )
        return Response(
            serialize_conversion(conversion),
            status=status.HTTP_201_CREATED,
        )


class ConversionDetailView(APIView):
    def get(self, request, conversion_id):
        farm = get_farm(request.user)
        conversion = scoped_get(
            UnitConversion,
            farm,
            conversion_id,
            "That conversion rule no longer exists.",
        )
        return Response(serialize_conversion(conversion))

    def put(self, request, conversion_id):
        farm = get_farm(request.user)
        from_unit = unit_lookup(
            farm, request.data.get("fromUnitId"), "fromUnitId"
        )
        to_unit = unit_lookup(
            farm, request.data.get("toUnitId"), "toUnitId"
        )
        with transaction.atomic():
            lock_conversion_farm(farm)
            conversion = scoped_get(
                UnitConversion,
                farm,
                conversion_id,
                "That conversion rule no longer exists.",
            )
            validate_conversion_rule(
                farm,
                from_unit,
                to_unit,
                existing_instance=conversion,
            )
            factor = parse_conversion_factor(request.data.get("factor"))
            conversion.from_unit = from_unit
            conversion.to_unit = to_unit
            conversion.factor = factor
            conversion.save(update_fields=["from_unit", "to_unit", "factor"])
        return Response(serialize_conversion(conversion))

    def delete(self, request, conversion_id):
        farm = get_farm(request.user)
        with transaction.atomic():
            lock_conversion_farm(farm)
            conversion = scoped_get(
                UnitConversion,
                farm,
                conversion_id,
                "That conversion rule no longer exists.",
            )
            conversion.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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

        source_data = _unit_data(from_unit)
        target_data = _unit_data(to_unit)
        is_identity = from_unit.pk == to_unit.pk
        rules = (
            []
            if is_identity
            else _conversion_rule_data(farm, from_unit, to_unit)
        )
        try:
            factor = (
                1
                if is_identity
                else conversion_factor(source_data, target_data, rules)
            )
            converted = convert_quantity(
                quantity, source_data, target_data, rules
            )
        except MissingConversionRuleError as exc:
            raise ApiError(str(exc), status.HTTP_404_NOT_FOUND)
        except UnitConversionError as exc:
            raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST)

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
        require_farm_setup_write(request)
        self._reject_status_input(request.data)
        farm = get_farm(request.user)
        field = self._field(farm, request.data.get("fieldId"))
        crop = self._crop(farm, request.data.get("cropId"))
        variety = self._variety(farm, request.data.get("varietyId"))
        if variety is not None and variety.crop_id != crop.id:
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
        cycle_type = self._cycle_type(request.data.get("cycleType"))
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
            cycle_type=cycle_type,
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
            return None
        try:
            return Variety.objects.get(farm=farm, pk=variety_id)
        except (Variety.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected variety does not exist.",
                status.HTTP_404_NOT_FOUND,
                "varietyId",
            )

    @staticmethod
    def _cycle_type(value):
        if value not in CycleType.values:
            message = (
                "Select whether this crop cycle is annual or perennial."
                if value in (None, "")
                else "Cycle type must be annual or perennial."
            )
            raise ApiError(
                message, status.HTTP_400_BAD_REQUEST, "cycleType"
            )
        return value

    @staticmethod
    def _reject_status_input(data):
        if "status" in data:
            raise ApiError(
                "Change crop cycle status through the close or reopen action.",
                status.HTTP_400_BAD_REQUEST,
                "status",
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
            amount = parse_decimal(
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
        model_field = {
            "expectedYield": "expected_yield",
            "expectedPrice": "expected_price",
        }[key]
        try:
            return CropCycle._meta.get_field(model_field).clean(
                amount, None
            )
        except ValidationError as exc:
            label = (
                "Expected yield"
                if key == "expectedYield"
                else "Expected price"
            )
            raise ApiError(
                f"{label} must fit within 14 digits and 4 decimal places.",
                status.HTTP_400_BAD_REQUEST,
                key,
            ) from exc


class CropCycleDetailView(APIView):
    def get(self, request, cycle_id):
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        return Response(serialize_cycle(cycle))

    def put(self, request, cycle_id):
        return self._update(request, cycle_id)

    def patch(self, request, cycle_id):
        return self._update(request, cycle_id)

    def _update(self, request, cycle_id):
        require_farm_setup_write(request)
        CropCycleListView._reject_status_input(request.data)
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be edited.",
                status.HTTP_409_CONFLICT,
            )
        if "fieldId" in request.data:
            cycle.field = CropCycleListView._field(
                farm, request.data.get("fieldId")
            )
        if "cropId" in request.data:
            cycle.crop = CropCycleListView._crop(
                farm, request.data.get("cropId")
            )
        if "varietyId" in request.data:
            cycle.variety = CropCycleListView._variety(
                farm, request.data.get("varietyId")
            )
        if cycle.variety_id and cycle.variety.crop_id != cycle.crop_id:
            raise ApiError(
                "The selected variety does not belong to the selected crop.",
                status.HTTP_400_BAD_REQUEST,
                "varietyId",
            )
        if "cycleType" in request.data:
            cycle.cycle_type = CropCycleListView._cycle_type(
                request.data.get("cycleType")
            )
        if "startDate" in request.data:
            cycle.start_date = parse_body_date(
                request.data,
                "startDate",
                "Start date is required.",
                "Start date must be a valid calendar date.",
            )
        if "endDate" in request.data:
            cycle.end_date = CropCycleListView._end_date(
                request.data.get("endDate"), cycle.start_date
            )
        elif cycle.end_date and cycle.end_date < cycle.start_date:
            raise ApiError(
                "End date cannot be before the start date.",
                status.HTTP_400_BAD_REQUEST,
                "endDate",
            )
        if "expectedYield" in request.data:
            cycle.expected_yield = CropCycleListView._optional_amount(
                request.data, "expectedYield"
            )
        if "expectedPrice" in request.data:
            cycle.expected_price = CropCycleListView._optional_amount(
                request.data, "expectedPrice"
            )
        cycle.save()
        return Response(serialize_cycle(cycle))

    def delete(self, request, cycle_id):
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "This crop cycle is closed and can no longer be deleted.",
                status.HTTP_409_CONFLICT,
            )
        cycle.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CropCycleCloseView(APIView):
    def post(self, request, cycle_id):
        require_farm_setup_write(request)
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


class CropCycleReopenView(APIView):
    def post(self, request, cycle_id):
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        cycle = scoped_get(
            CropCycle, farm, cycle_id, "That crop cycle no longer exists."
        )
        if cycle.status == CycleStatus.OPEN:
            raise ApiError(
                "This crop cycle is already open.",
                status.HTTP_409_CONFLICT,
            )
        cycle.status = CycleStatus.OPEN
        cycle.save(update_fields=["status"])
        return Response(serialize_cycle(cycle))


class ActivityTypeListView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_activity_type(activity_type)
                for activity_type in farm.activity_types.all()
            ]
        )

    def post(self, request):
        require_farm_setup_write(request)
        farm = get_farm(request.user)
        name = require_name(request.data, "name", "Activity type")
        category = self._category(request.data.get("category"))
        inputs = self._inputs(request.data.get("inputs", []))
        labour_hours = self._labour_hours(
            request.data.get("labourHours", 0)
        )
        equipment = self._equipment(request.data.get("equipment", ""))
        ensure_unique_farm_name(
            ActivityType, farm, name, "Activity type"
        )
        activity_type = ActivityType(
            farm=farm,
            name=name,
            category=category,
            standard=False,
            default_inputs=inputs,
            default_labour_hours=labour_hours,
            default_equipment=equipment,
        )
        save_unique_farm_name(activity_type, "Activity type")
        return Response(
            serialize_activity_type(activity_type),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _category(value):
        if not isinstance(value, str) or not value.strip():
            raise ApiError(
                "An activity type category is required.",
                status.HTTP_400_BAD_REQUEST,
                "category",
            )
        text = value.strip()
        if len(text) > 32:
            raise ApiError(
                "Activity type category must be 32 characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
                "category",
            )
        return text

    @staticmethod
    def _inputs(value):
        if not isinstance(value, list):
            raise ApiError(
                "Inputs must be a list.",
                status.HTTP_400_BAD_REQUEST,
                "inputs",
            )
        parsed = []
        for item in value:
            if not isinstance(item, dict):
                raise ApiError(
                    "Each input must include an item name and quantity.",
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                )
            item_name = item.get("itemName")
            if not isinstance(item_name, str) or not item_name.strip():
                raise ApiError(
                    "Each input must include an item name.",
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                )
            item_name = item_name.strip()
            if len(item_name) > 255:
                raise ApiError(
                    "Input item names must be 255 characters or fewer.",
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                )
            try:
                quantity = parse_decimal(
                    item.get("quantity"),
                    "quantity",
                    "Input quantity is required.",
                    "Input quantity must be a number.",
                    positive_message="Input quantity must be greater than zero.",
                )
                ActivityInputNeed._meta.get_field(
                    "quantity"
                ).run_validators(quantity)
            except (ValueError, ValidationError) as exc:
                message = (
                    "Input quantity must be a positive number with at most "
                    "four decimal places."
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                raise ApiError(
                    message,
                    status.HTTP_400_BAD_REQUEST,
                    "inputs",
                ) from exc
            parsed.append(
                {"itemName": item_name, "quantity": str(quantity)}
            )
        return parsed

    @staticmethod
    def _labour_hours(value):
        try:
            hours = parse_decimal(
                value,
                "labourHours",
                "Labour hours are required.",
                "Labour hours must be a number.",
                negative_message="Labour hours cannot be negative.",
            )
            ActivityType._meta.get_field(
                "default_labour_hours"
            ).run_validators(hours)
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "labourHours"
            ) from exc
        except ValidationError as exc:
            raise ApiError(
                "Labour hours must be non-negative with at most four "
                "decimal places.",
                status.HTTP_400_BAD_REQUEST,
                "labourHours",
            ) from exc
        return hours

    @staticmethod
    def _equipment(value):
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ApiError(
                "Equipment must be text.",
                status.HTTP_400_BAD_REQUEST,
                "equipment",
            )
        text = value.strip()
        if len(text) > 255:
            raise ApiError(
                "Equipment must be 255 characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
                "equipment",
            )
        return text


class ActivityTypeDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, type_id):
        farm = get_farm(request.user)
        activity_type = scoped_get(
            ActivityType,
            farm,
            type_id,
            "That activity type no longer exists.",
        )
        return Response(serialize_activity_type(activity_type))

    def put(self, request, type_id):
        return self._update(request, type_id, partial=False)

    def patch(self, request, type_id):
        return self._update(request, type_id, partial=True)

    def _update(self, request, type_id, *, partial):
        farm = get_farm(request.user)
        activity_type = scoped_get(
            ActivityType,
            farm,
            type_id,
            "That activity type no longer exists.",
        )
        require_farm_setup_write(request)
        if activity_type.standard:
            raise ApiError(
                "Standard activity types cannot be changed.",
                status.HTTP_409_CONFLICT,
            )

        data = request.data
        if not partial or "name" in data:
            name = require_name(data, "name", "Activity type")
            ensure_unique_farm_name(
                ActivityType, farm, name, "Activity type", activity_type
            )
            activity_type.name = name
        if not partial or "category" in data:
            activity_type.category = ActivityTypeListView._category(
                data.get("category")
            )
        if not partial or "inputs" in data:
            activity_type.default_inputs = ActivityTypeListView._inputs(
                data.get("inputs", [])
            )
        if not partial or "labourHours" in data:
            activity_type.default_labour_hours = (
                ActivityTypeListView._labour_hours(data.get("labourHours", 0))
            )
        if not partial or "equipment" in data:
            activity_type.default_equipment = ActivityTypeListView._equipment(
                data.get("equipment", "")
            )
        save_unique_farm_name(activity_type, "Activity type")
        return Response(serialize_activity_type(activity_type))

    def delete(self, request, type_id):
        farm = get_farm(request.user)
        activity_type = scoped_get(
            ActivityType,
            farm,
            type_id,
            "That activity type no longer exists.",
        )
        require_farm_setup_write(request)
        if activity_type.standard:
            raise ApiError(
                "Standard activity types cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        try:
            activity_type.delete()
        except (ProtectedError, RestrictedError):
            raise ApiError(
                "An activity type referenced by an activity cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityCycleListView(APIView):
    def get(self, request):
        if request.user.role == Role.WORKER:
            cycles = CropCycle.objects.filter(
                activities__in=activity_queryset_for(request)
            ).distinct()
        else:
            farm = get_activity_farm(request.user)
            cycles = farm.crop_cycles.all()
        return Response([
            serialize_cycle_ref(cycle)
            for cycle in cycles.select_related("field", "crop")
        ])


class ActivityListView(APIView):
    def get(self, request):
        activities = activity_queryset_for(request).select_related(
            "cycle", "type"
        ).prefetch_related("input_needs", "labour_records", "assignees")
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            try:
                cycle_id = UUID(cycle_id)
            except (TypeError, ValueError):
                return Response([])
            activities = activities.filter(cycle_id=cycle_id)
        return Response(
            [serialize_activity(activity) for activity in activities]
        )

    def post(self, request):
        require_activity_manager(request)
        farm = get_activity_farm(request.user)
        cycle = self._cycle(farm, request.data.get("cycleId"))
        activity_type = self._type(farm, request.data.get("typeId"))
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "Activities cannot be created in a closed crop cycle.",
                status.HTTP_409_CONFLICT,
            )
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
    def get(self, request, activity_id):
        activity = get_visible_activity(request, activity_id)
        return Response(serialize_activity(activity))

    def put(self, request, activity_id):
        require_activity_manager(request)
        farm = get_activity_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        ensure_activity_cycle_open(activity)
        cycle = ActivityListView._cycle(
            farm, request.data.get("cycleId")
        )
        if cycle.status == CycleStatus.CLOSED:
            raise ApiError(
                "Activities cannot be moved into a closed crop cycle.",
                status.HTTP_409_CONFLICT,
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

    def delete(self, request, activity_id):
        require_activity_manager(request)
        farm = get_activity_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        ensure_activity_cycle_open(activity)
        activity.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ActivityStatusView(APIView):
    def put(self, request, activity_id):
        if request.user.role != Role.WORKER:
            require_activity_manager(request)
        activity = get_visible_activity(request, activity_id)
        ensure_activity_cycle_open(activity)
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


class ActivityAssigneesView(APIView):
    def put(self, request, activity_id):
        require_activity_manager(request)
        farm = get_activity_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        ensure_activity_cycle_open(activity)
        if not isinstance(request.data, dict):
            raise ApiError(
                "assignedWorkerIds must be provided in an object.",
                status.HTTP_400_BAD_REQUEST,
                "assignedWorkerIds",
            )
        worker_ids = request.data.get("assignedWorkerIds")
        if not isinstance(worker_ids, list):
            raise ApiError(
                "assignedWorkerIds must be an array.",
                status.HTTP_400_BAD_REQUEST,
                "assignedWorkerIds",
            )
        try:
            worker_ids = [UUID(worker_id) for worker_id in worker_ids]
        except (AttributeError, TypeError, ValueError):
            raise ApiError(
                "assignedWorkerIds must contain valid user IDs.",
                status.HTTP_400_BAD_REQUEST,
                "assignedWorkerIds",
            )
        worker_ids = set(worker_ids)
        valid_ids = set(
            User.objects.filter(
                pk__in=worker_ids,
                role=Role.WORKER,
            )
            .filter(Q(member_farms=farm) | Q(farm=farm))
            .values_list("pk", flat=True)
        )
        if valid_ids != worker_ids:
            raise ApiError(
                "Each assigned user must be a worker belonging to this farm.",
                status.HTTP_400_BAD_REQUEST,
                "assignedWorkerIds",
            )
        activity.assignees.set(valid_ids)
        activity = Activity.objects.prefetch_related("assignees").get(
            pk=activity.pk
        )
        return Response(serialize_activity(activity))


class ActivityResourceNeedsView(APIView):
    def put(self, request, activity_id):
        require_activity_manager(request)
        farm = get_activity_farm(request.user)
        activity = scoped_get(
            Activity, farm, activity_id, "That activity no longer exists."
        )
        ensure_activity_cycle_open(activity)
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


PLANNED_LINE_TYPES = {
    "planned-inputs": (PlannedInput, "item", "itemId", "quantity"),
    "planned-labour": (PlannedLabour, None, None, "hours"),
    "planned-equipment": (PlannedEquipment, "equipment", "equipmentId", "hours"),
}


class PlannedLineView(APIView):
    def _activity(self, request, activity_id, write=False):
        if write:
            require_activity_manager(request)
        activity = get_visible_activity(request, activity_id)
        if write:
            ensure_activity_cycle_open(activity)
        return activity

    def _line(self, model, activity, line_id):
        try:
            return model.objects.get(activity=activity, pk=line_id)
        except (model.DoesNotExist, ValueError, ValidationError):
            raise ApiError("That planned line does not exist.", status.HTTP_404_NOT_FOUND)

    def _serialize(self, line, reference, api_reference, amount):
        data = {
            "id": str(line.pk),
            "activityId": str(line.activity_id),
            amount: as_number(getattr(line, amount)),
        }
        if reference:
            data[api_reference] = str(getattr(line, f"{reference}_id"))
        return data

    def get(self, request, activity_id, kind, line_id=None):
        model, reference, api_reference, amount = PLANNED_LINE_TYPES[kind]
        activity = self._activity(request, activity_id)
        if line_id is not None:
            line = self._line(model, activity, line_id)
            return Response(self._serialize(line, reference, api_reference, amount))
        return Response([
            self._serialize(line, reference, api_reference, amount)
            for line in model.objects.filter(activity=activity)
        ])

    def _save(self, request, activity_id, kind, line_id=None, partial=False):
        model, reference, api_reference, amount = PLANNED_LINE_TYPES[kind]
        activity = self._activity(request, activity_id, write=True)
        line = (
            self._line(model, activity, line_id)
            if line_id is not None else model(activity=activity)
        )
        data = request.data
        if not isinstance(data, dict):
            raise ApiError("Expected an object.", status.HTTP_400_BAD_REQUEST)
        if reference and (not partial or api_reference in data):
            reference_model = InventoryItem if reference == "item" else Equipment
            value = data.get(api_reference)
            if value is not None and not isinstance(value, str):
                raise ApiError("Invalid reference.", status.HTTP_400_BAD_REQUEST, api_reference)
            target = scoped_get(
                reference_model, activity.farm, value,
                "The selected resource does not exist.", api_reference,
            )
            setattr(line, reference, target)
        if not partial or amount in data:
            value = parse_body_decimal(
                data, amount, f"{amount} is required.", f"{amount} must be a number.",
                positive_message=f"{amount} must be greater than zero.",
            )
            try:
                model._meta.get_field(amount).run_validators(value)
            except ValidationError as exc:
                raise ApiError(
                    f"{amount} must fit within 10 integer digits and 4 decimal places.",
                    status.HTTP_400_BAD_REQUEST, amount,
                ) from exc
            setattr(line, amount, value)
        if reference:
            duplicates = model.objects.filter(
                activity=activity, **{reference: getattr(line, reference)}
            ).exclude(pk=line.pk)
            if duplicates.exists():
                raise ApiError("Resource is already planned.", status.HTTP_409_CONFLICT, api_reference)
        try:
            with transaction.atomic():
                line.save()
        except IntegrityError as exc:
            raise ApiError("Resource is already planned.", status.HTTP_409_CONFLICT, api_reference) from exc
        return Response(
            self._serialize(line, reference, api_reference, amount),
            status=status.HTTP_201_CREATED if line_id is None else status.HTTP_200_OK,
        )

    def post(self, request, activity_id, kind, line_id=None):
        if line_id is not None:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save(request, activity_id, kind)

    def put(self, request, activity_id, kind, line_id=None):
        if line_id is None:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save(request, activity_id, kind, line_id)

    def patch(self, request, activity_id, kind, line_id=None):
        if line_id is None:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        return self._save(request, activity_id, kind, line_id, partial=True)

    def delete(self, request, activity_id, kind, line_id=None):
        if line_id is None:
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
        model = PLANNED_LINE_TYPES[kind][0]
        activity = self._activity(request, activity_id, write=True)
        self._line(model, activity, line_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerListView(APIView):
    def get(self, request):
        farm = get_inventory_farm(request)
        return Response(
            [
                serialize_worker(worker)
                for worker in farm.workers.select_related("user")
            ]
        )

    def post(self, request):
        farm = get_inventory_farm(request)
        worker = self._save(farm, None, request.data)
        return Response(
            serialize_worker(worker), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _save(farm, worker, data):
        name = require_name(data, "name", "Worker")
        user = None
        user_id = data.get("userId")
        if user_id not in (None, ""):
            try:
                user = User.objects.get(pk=user_id)
            except (User.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "The selected user does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "userId",
                )
        if worker is None:
            return Worker.objects.create(farm=farm, name=name, user=user)
        worker.name = name
        worker.user = user
        worker.save()
        return worker


class WorkerDetailView(APIView):
    def get(self, request, worker_id):
        farm = get_inventory_farm(request)
        worker = scoped_get(
            Worker, farm, worker_id, "That worker no longer exists."
        )
        return Response(serialize_worker(worker))

    def put(self, request, worker_id):
        farm = get_inventory_farm(request)
        worker = scoped_get(
            Worker, farm, worker_id, "That worker no longer exists."
        )
        worker = WorkerListView._save(farm, worker, request.data)
        return Response(serialize_worker(worker))

    def delete(self, request, worker_id):
        farm = get_inventory_farm(request)
        worker = scoped_get(
            Worker, farm, worker_id, "That worker no longer exists."
        )
        if worker.labour_records.exists():
            raise ApiError(
                "A worker with labour records cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        worker.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LabourRecordListView(APIView):
    def get(self, request):
        farm = get_inventory_farm(request)
        records = farm.labour_records.select_related("worker", "activity")
        activity_id = request.query_params.get(
            "activityId", request.query_params.get("activity")
        )
        if activity_id is not None:
            try:
                activity_id = Activity._meta.pk.to_python(activity_id)
            except (AttributeError, TypeError, ValueError, ValidationError):
                raise ApiError(
                    "The activity filter must be a valid activity ID.",
                    status.HTTP_400_BAD_REQUEST,
                    "activityId",
                )
            records = records.filter(activity_id=activity_id)
        return Response(
            [serialize_labour_record(record) for record in records]
        )

    def post(self, request):
        farm = get_inventory_farm(request)
        record = self._save(farm, None, request.data)
        return Response(
            serialize_labour_record(record), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _save(farm, record, data):
        worker_id = data.get("workerId")
        try:
            worker = Worker.objects.get(farm=farm, pk=worker_id)
        except (Worker.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected worker does not exist.",
                status.HTTP_404_NOT_FOUND,
                "workerId",
            )

        activity_id = data.get("activityId")
        try:
            activity = Activity.objects.get(farm=farm, pk=activity_id)
        except (Activity.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected activity does not exist.",
                status.HTTP_404_NOT_FOUND,
                "activityId",
            )

        try:
            hours = parse_decimal(
                data.get("hours"),
                "hours",
                "Hours are required.",
                "Hours must be a number.",
                positive_message="Hours must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "hours"
            )
        try:
            hourly_cost = parse_decimal(
                data.get("hourlyCost", data.get("hourly_cost")),
                "hourly_cost",
                "Hourly cost is required.",
                "Hourly cost must be a number.",
                positive_message="Hourly cost must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "hourly_cost"
            )
        record_date = parse_body_date(
            data,
            "date",
            "Date is required.",
            "Date must be a valid calendar date.",
        )
        if record is None:
            return LabourRecord.objects.create(
                farm=farm,
                worker=worker,
                activity=activity,
                hours=hours,
                hourly_cost=hourly_cost,
                date=record_date,
            )
        record.worker = worker
        record.activity = activity
        record.hours = hours
        record.hourly_cost = hourly_cost
        record.date = record_date
        record.save()
        return record


class LabourRecordDetailView(APIView):
    def get(self, request, record_id):
        farm = get_inventory_farm(request)
        record = scoped_get(
            LabourRecord,
            farm,
            record_id,
            "That labour record no longer exists.",
        )
        return Response(serialize_labour_record(record))

    def put(self, request, record_id):
        farm = get_inventory_farm(request)
        record = scoped_get(
            LabourRecord,
            farm,
            record_id,
            "That labour record no longer exists.",
        )
        record = LabourRecordListView._save(farm, record, request.data)
        return Response(serialize_labour_record(record))

    def delete(self, request, record_id):
        farm = get_inventory_farm(request)
        record = scoped_get(
            LabourRecord,
            farm,
            record_id,
            "That labour record no longer exists.",
        )
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EquipmentListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_equipment(equipment)
                for equipment in farm.equipment.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        equipment = self._save(farm, None, request.data)
        return Response(
            serialize_equipment(equipment), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _save(farm, equipment, data):
        name = require_name(data, "name", "Equipment")
        if equipment is None:
            return Equipment.objects.create(farm=farm, name=name)
        equipment.name = name
        equipment.save()
        return equipment


class EquipmentDetailView(APIView):
    def get(self, request, equipment_id):
        farm = get_farm(request.user)
        equipment = scoped_get(
            Equipment,
            farm,
            equipment_id,
            "That equipment no longer exists.",
        )
        return Response(serialize_equipment(equipment))

    def put(self, request, equipment_id):
        farm = get_farm(request.user)
        equipment = scoped_get(
            Equipment,
            farm,
            equipment_id,
            "That equipment no longer exists.",
        )
        equipment = EquipmentListView._save(farm, equipment, request.data)
        return Response(serialize_equipment(equipment))

    def delete(self, request, equipment_id):
        farm = get_farm(request.user)
        equipment = scoped_get(
            Equipment, farm, equipment_id, "That equipment no longer exists."
        )
        if equipment.usages.exists():
            raise ApiError(
                "Equipment with usage records cannot be deleted.",
                status.HTTP_409_CONFLICT,
            )
        try:
            equipment.delete()
        except ProtectedError as exc:
            raise ApiError(
                "Equipment referenced by planned lines cannot be deleted.",
                status.HTTP_409_CONFLICT,
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class EquipmentUsageListView(APIView):
    @staticmethod
    def _validate_source_precision(value, api_field, model_field, label):
        try:
            EquipmentUsage._meta.get_field(model_field).run_validators(value)
        except ValidationError as exc:
            raise ApiError(
                f"{label} must have at most four decimal places and fit "
                "within 14 digits.",
                status.HTTP_400_BAD_REQUEST,
                api_field,
            ) from exc

    def get(self, request):
        farm = get_farm(request.user)
        usages = farm.equipment_usages.select_related(
            "equipment", "activity"
        )
        activity_id = request.query_params.get(
            "activityId", request.query_params.get("activity")
        )
        if activity_id is not None:
            try:
                activity_id = Activity._meta.pk.to_python(activity_id)
            except (AttributeError, TypeError, ValueError, ValidationError):
                raise ApiError(
                    "The activity filter must be a valid activity ID.",
                    status.HTTP_400_BAD_REQUEST,
                    "activityId",
                )
            usages = usages.filter(activity_id=activity_id)
        return Response(
            [serialize_equipment_usage(usage) for usage in usages]
        )

    def post(self, request):
        farm = get_farm(request.user)
        usage = self._save(farm, None, request.data)
        return Response(
            serialize_equipment_usage(usage),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _save(farm, usage, data):
        equipment_id = data.get("equipmentId")
        try:
            equipment = Equipment.objects.get(farm=farm, pk=equipment_id)
        except (Equipment.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected equipment does not exist.",
                status.HTTP_404_NOT_FOUND,
                "equipmentId",
            )

        activity_id = data.get("activityId")
        try:
            activity = Activity.objects.get(farm=farm, pk=activity_id)
        except (Activity.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "The selected activity does not exist.",
                status.HTTP_404_NOT_FOUND,
                "activityId",
            )

        try:
            hours = parse_decimal(
                data.get("hours"),
                "hours",
                "Hours are required.",
                "Hours must be a number.",
                positive_message="Hours must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST, "hours")
        EquipmentUsageListView._validate_source_precision(
            hours, "hours", "hours", "Hours"
        )

        cost_per_hour_keys = ("costPerHour", "cost_per_hour")
        total_cost_keys = ("totalCost", "total_cost")
        has_cost_per_hour = any(
            data.get(key) not in (None, "") for key in cost_per_hour_keys
        )
        has_total_cost = any(
            data.get(key) not in (None, "") for key in total_cost_keys
        )
        if has_cost_per_hour == has_total_cost:
            raise ApiError(
                "Provide exactly one of costPerHour or totalCost.",
                status.HTTP_400_BAD_REQUEST,
                "costPerHour",
            )

        cost_per_hour = None
        total_cost = None
        if has_cost_per_hour:
            cost_per_hour_raw = next(
                data[key]
                for key in cost_per_hour_keys
                if data.get(key) not in (None, "")
            )
            try:
                cost_per_hour = parse_decimal(
                    cost_per_hour_raw,
                    "costPerHour",
                    "Cost per hour is required.",
                    "Cost per hour must be a number.",
                    negative_message="Cost per hour cannot be negative.",
                )
                EquipmentUsageListView._validate_source_precision(
                    cost_per_hour,
                    "costPerHour",
                    "cost_per_hour",
                    "Cost per hour",
                )
            except ValueError as exc:
                raise ApiError(
                    str(exc), status.HTTP_400_BAD_REQUEST, "costPerHour"
                )
        else:
            total_cost_raw = next(
                data[key]
                for key in total_cost_keys
                if data.get(key) not in (None, "")
            )
            try:
                total_cost = parse_decimal(
                    total_cost_raw,
                    "totalCost",
                    "Total cost is required.",
                    "Total cost must be a number.",
                    negative_message="Total cost cannot be negative.",
                )
                EquipmentUsageListView._validate_source_precision(
                    total_cost, "totalCost", "total_cost", "Total cost"
                )
            except ValueError as exc:
                raise ApiError(
                    str(exc), status.HTTP_400_BAD_REQUEST, "totalCost"
                )

        record_date = parse_body_date(
            data,
            "date",
            "Date is required.",
            "Date must be a valid calendar date.",
        )
        if usage is None:
            return EquipmentUsage.objects.create(
                farm=farm,
                equipment=equipment,
                activity=activity,
                hours=hours,
                cost_per_hour=cost_per_hour,
                total_cost=total_cost,
                date=record_date,
            )
        usage.equipment = equipment
        usage.activity = activity
        usage.hours = hours
        usage.cost_per_hour = cost_per_hour
        usage.total_cost = total_cost
        usage.date = record_date
        usage.save()
        return usage


class EquipmentUsageDetailView(APIView):
    def get(self, request, usage_id):
        farm = get_farm(request.user)
        usage = scoped_get(
            EquipmentUsage,
            farm,
            usage_id,
            "That equipment usage no longer exists.",
        )
        return Response(serialize_equipment_usage(usage))

    def put(self, request, usage_id):
        farm = get_farm(request.user)
        usage = scoped_get(
            EquipmentUsage,
            farm,
            usage_id,
            "That equipment usage no longer exists.",
        )
        usage = EquipmentUsageListView._save(farm, usage, request.data)
        return Response(serialize_equipment_usage(usage))

    def delete(self, request, usage_id):
        farm = get_farm(request.user)
        usage = scoped_get(
            EquipmentUsage,
            farm,
            usage_id,
            "That equipment usage no longer exists.",
        )
        usage.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryItemListView(APIView):
    def get(self, request):
        farm = get_inventory_farm(request)
        return Response(
            [
                serialize_inventory_item(item)
                for item in farm.inventory_items.prefetch_related("movements")
            ]
        )

    def post(self, request):
        farm = get_inventory_farm(request)
        item = self._save(farm, None, request.data)
        return Response(
            serialize_inventory_item(item),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _save(farm, item, data):
        if not hasattr(data, "get"):
            raise ApiError(
                "Inventory item details must be an object.",
                status.HTTP_400_BAD_REQUEST,
            )
        name = require_name(data, "name", "Inventory item")
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
        if (
            item is not None
            and item.unit_id != unit.id
            and item.movements.exists()
        ):
            raise ApiError(
                "Cannot change the unit of an item with stock movements.",
                status.HTTP_409_CONFLICT,
                "unitId",
            )
        reorder_value = data.get("reorderLevel")
        reorder_level = None
        if reorder_value not in (None, ""):
            reorder_level = parse_body_decimal(
                data,
                "reorderLevel",
                "Reorder level must be a number.",
                "Reorder level must be a number.",
                negative_message="Reorder level cannot be negative.",
            )
            try:
                InventoryItem._meta.get_field(
                    "reorder_level"
                ).run_validators(reorder_level)
            except ValidationError as exc:
                raise ApiError(
                    "Reorder level must be a non-negative number with at "
                    "most four decimal places.",
                    status.HTTP_400_BAD_REQUEST,
                    "reorderLevel",
                ) from exc
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
    def get(self, request, item_id):
        farm = get_inventory_farm(request)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item no longer exists.",
        )
        return Response(serialize_inventory_item(item))

    def put(self, request, item_id):
        farm = get_inventory_farm(request)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item no longer exists.",
        )
        item = InventoryItemListView._save(farm, item, request.data)
        return Response(serialize_inventory_item(item))

    def delete(self, request, item_id):
        farm = get_inventory_farm(request)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item no longer exists.",
        )
        if item.movements.exists():
            raise ApiError(
                "Cannot delete an inventory item with stock movements.",
                status.HTTP_409_CONFLICT,
            )
        try:
            item.delete()
        except ProtectedError as exc:
            raise ApiError(
                "Inventory items referenced by planned lines cannot be deleted.",
                status.HTTP_409_CONFLICT,
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class ItemMovementListView(APIView):
    def get(self, request, item_id):
        farm = get_inventory_farm(request)
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
        farm = get_inventory_farm(request)
        item = scoped_get(
            InventoryItem,
            farm,
            item_id,
            "That inventory item does not exist.",
            "itemId",
        )
        movement = StockMovementListView._create(
            farm, request.data, path_item=item
        )
        return Response(
            serialize_movement(movement),
            status=status.HTTP_201_CREATED,
        )


class StockMovementListView(APIView):
    def get(self, request):
        farm = get_inventory_farm(request)
        return Response(
            [
                serialize_movement(movement)
                for movement in farm.stock_movements.all()
            ]
        )

    def post(self, request):
        farm = get_inventory_farm(request)
        movement = self._create(farm, request.data)
        return Response(
            serialize_movement(movement),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _create(farm, data, *, path_item=None):
        if not hasattr(data, "get"):
            raise ApiError(
                "Stock movement details must be an object.",
                status.HTTP_400_BAD_REQUEST,
            )
        item_id = data.get("itemId")
        if item_id in (None, ""):
            raise ApiError(
                "Select an inventory item.",
                status.HTTP_400_BAD_REQUEST,
                "itemId",
            )
        if path_item is not None and str(item_id) != str(path_item.id):
            raise ApiError(
                "The itemId must match the path.",
                status.HTTP_400_BAD_REQUEST,
                "itemId",
            )
        if path_item is None:
            try:
                item = InventoryItem.objects.get(farm=farm, pk=item_id)
            except (
                InventoryItem.DoesNotExist,
                TypeError,
                ValueError,
                ValidationError,
            ):
                raise ApiError(
                    "That inventory item does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "itemId",
                )
        else:
            item = path_item

        unit_id = data.get("unitId")
        if unit_id not in (None, ""):
            try:
                unit = Unit.objects.get(farm=farm, pk=unit_id)
            except (
                Unit.DoesNotExist,
                TypeError,
                ValueError,
                ValidationError,
            ):
                raise ApiError(
                    "That unit does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "unitId",
                )
            if unit.id != item.unit_id:
                raise ApiError(
                    "Stock movement quantities must use the item's unit.",
                    status.HTTP_400_BAD_REQUEST,
                    "unitId",
                )

        movement_type = str(data.get("type") or "").strip()
        if movement_type not in MovementType.values:
            raise ApiError(
                "Movement type must be one of: purchase, usage, adjustment.",
                status.HTTP_400_BAD_REQUEST,
                "type",
            )
        try:
            quantity = parse_decimal(
                data.get("quantity"),
                "quantity",
                "Quantity is required.",
                "Quantity must be a number.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "quantity"
            ) from exc
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
        try:
            StockMovement._meta.get_field("quantity").run_validators(
                quantity
            )
        except ValidationError as exc:
            raise ApiError(
                "Quantity must have at most four decimal places.",
                status.HTTP_400_BAD_REQUEST,
                "quantity",
            ) from exc

        movement_date = parse_body_date(
            data,
            "date",
            "Date is required.",
            "Date must be a valid calendar date.",
        )
        unit_cost = None
        if data.get("unitCost") not in (None, ""):
            unit_cost = parse_body_decimal(
                data,
                "unitCost",
                "Unit cost must be a number.",
                "Unit cost must be a number.",
                negative_message="Unit cost cannot be negative.",
            )
            try:
                StockMovement._meta.get_field(
                    "unit_cost"
                ).run_validators(unit_cost)
            except ValidationError as exc:
                raise ApiError(
                    "Unit cost must be non-negative with at most four "
                    "decimal places.",
                    status.HTTP_400_BAD_REQUEST,
                    "unitCost",
                ) from exc

        activity = None
        activity_id = data.get("activityId")
        if activity_id not in (None, ""):
            try:
                activity = Activity.objects.get(farm=farm, pk=activity_id)
            except (
                Activity.DoesNotExist,
                TypeError,
                ValueError,
                ValidationError,
            ):
                raise ApiError(
                    "The selected activity does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "activityId",
                )

        expense = None
        expense_id = data.get("expenseId")
        if expense_id not in (None, ""):
            try:
                expense = Expense.objects.get(farm=farm, pk=expense_id)
            except (
                Expense.DoesNotExist,
                TypeError,
                ValueError,
                ValidationError,
            ):
                raise ApiError(
                    "The selected expense does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "expenseId",
                )

        if movement_type in (
            MovementType.PURCHASE,
            MovementType.ADJUSTMENT,
        ):
            quantity_delta = quantity
        else:
            quantity_delta = -quantity
        with transaction.atomic():
            item = InventoryItem.objects.select_for_update().get(
                farm=farm, pk=item.pk
            )
            available = item.current_quantity()
            if quantity_delta < 0 and -quantity_delta > available:
                raise ApiError(
                    "Movement would make stock negative "
                    f"(available: {format_amount(available)}).",
                    status.HTTP_400_BAD_REQUEST,
                    "quantity",
                )
            movement = StockMovement.objects.create(
                farm=farm,
                item=item,
                type=movement_type,
                quantity=quantity,
                date=movement_date,
                unit_cost=unit_cost,
                activity=activity,
                expense=expense,
                note=optional_text(data, "note"),
            )
        return movement


class StockMovementDetailView(APIView):
    def get(self, request, movement_id):
        farm = get_inventory_farm(request)
        movement = scoped_get(
            StockMovement,
            farm,
            movement_id,
            "That stock movement no longer exists.",
        )
        return Response(serialize_movement(movement))

    def put(self, request, movement_id):
        farm = get_inventory_farm(request)
        scoped_get(
            StockMovement,
            farm,
            movement_id,
            "That stock movement no longer exists.",
        )
        raise ApiError(
            "Posted stock movements cannot be edited; create a reversal "
            "and replacement movement.",
            status.HTTP_409_CONFLICT,
        )

    def delete(self, request, movement_id):
        farm = get_inventory_farm(request)
        scoped_get(
            StockMovement,
            farm,
            movement_id,
            "That stock movement no longer exists.",
        )
        raise ApiError(
            "Posted stock movements cannot be deleted; create a reversal "
            "and replacement movement.",
            status.HTTP_409_CONFLICT,
        )


class ExpenseCategoryListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        ensure_default_expense_categories(farm)
        return Response(
            [
                serialize_expense_category(category)
                for category in farm.expense_categories.all()
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        ensure_default_expense_categories(farm)
        name = require_text(
            request.data, "name", "Category name is required."
        )
        max_length = ExpenseCategoryRecord._meta.get_field("name").max_length
        if len(name) > max_length:
            raise ApiError(
                f"Category name must be {max_length} characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
                "name",
            )
        if farm.expense_categories.filter(name__iexact=name).exists():
            raise ApiError(
                "A category with that name already exists.",
                status.HTTP_400_BAD_REQUEST,
                "name",
            )
        category = ExpenseCategoryRecord.objects.create(
            farm=farm, name=name
        )
        return Response(
            serialize_expense_category(category),
            status=status.HTTP_201_CREATED,
        )


class ExpenseCategoryDetailView(APIView):
    def get(self, request, category_id):
        farm = get_farm(request.user)
        ensure_default_expense_categories(farm)
        category = scoped_get(
            ExpenseCategoryRecord,
            farm,
            category_id,
            "That expense category no longer exists.",
        )
        return Response(serialize_expense_category(category))


class ExpenseListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                serialize_expense(expense)
                for expense in farm.expenses.select_related(
                    "category_record", "supplier_record"
                ).prefetch_related("attachments")
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        values = self._validate(request.data, farm)
        expense = Expense.objects.create(farm=farm, **values)
        return Response(
            serialize_expense(expense),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _validate(data, farm, default_status=ExpenseStatus.DRAFT):
        ensure_default_expense_categories(farm)
        category_id = data.get("categoryId")
        category_name = str(data.get("category") or "").strip()
        if category_id not in (None, ""):
            category = scoped_get(
                ExpenseCategoryRecord,
                farm,
                category_id,
                "The selected expense category does not exist.",
                "categoryId",
            )
        elif category_name:
            category = farm.expense_categories.filter(
                name__iexact=category_name
            ).first()
            if category is None:
                raise ApiError(
                    "The selected expense category does not exist.",
                    status.HTTP_400_BAD_REQUEST,
                    "category",
                )
        else:
            raise ApiError(
                "Category is required.",
                status.HTTP_400_BAD_REQUEST,
                "categoryId",
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
        if amount <= 0:
            raise ApiError(
                "Amount must be greater than zero.",
                status.HTTP_400_BAD_REQUEST,
                "amount",
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
        raw_status = data.get("status")
        expense_status = str(
            default_status if raw_status is None else raw_status
        ).strip()
        if expense_status not in ExpenseStatus.values:
            raise ApiError(
                "Status must be draft or posted.",
                status.HTTP_400_BAD_REQUEST,
                "status",
            )
        supplier_record = None
        supplier_text = optional_text(data, "supplier")
        supplier_id = data.get("supplierId")
        if supplier_id not in (None, ""):
            supplier_record = scoped_get(
                Supplier,
                farm,
                supplier_id,
                "The selected supplier does not exist.",
                "supplierId",
            )
            supplier_text = None
        attachment_reference = optional_text(
            data, "attachmentReference"
        )
        attachment_max_length = Expense._meta.get_field(
            "attachment_reference"
        ).max_length
        if len(attachment_reference) > attachment_max_length:
            raise ApiError(
                "Attachment reference must be "
                f"{attachment_max_length} characters or fewer.",
                status.HTTP_400_BAD_REQUEST,
                "attachmentReference",
            )
        cycle = None
        cycle_id = data.get("cycleId")
        if cycle_id not in (None, ""):
            try:
                cycle = CropCycle.objects.get(farm=farm, pk=cycle_id)
            except (CropCycle.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "The selected crop cycle does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "cycleId",
                )
        return {
            "category_record": category,
            "category": category.name,
            "amount": amount,
            "date": expense_date,
            "supplier": supplier_text or None,
            "supplier_record": supplier_record,
            "attachment_reference": attachment_reference or "",
            "status": expense_status,
            "cycle": cycle,
        }


class ExpenseDetailView(APIView):
    def get(self, request, expense_id):
        farm = get_farm(request.user)
        expense = scoped_get(
            Expense, farm, expense_id, "That expense no longer exists."
        )
        return Response(serialize_expense(expense))

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
        values = ExpenseListView._validate(
            request.data, farm, default_status=expense.status
        )
        for field, value in values.items():
            setattr(expense, field, value)
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


class RecurringExpenseTemplateListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        templates = farm.recurring_expense_templates.select_related("category")
        return Response(
            [
                serialize_recurring_expense_template(template)
                for template in templates
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        requested_farm_id = request.data.get("farmId")
        if (
            requested_farm_id not in (None, "")
            and str(requested_farm_id) != str(farm.id)
        ):
            raise ApiError(
                "You do not have access to that farm.",
                status.HTTP_403_FORBIDDEN,
                "farmId",
            )
        values = self._validate(request.data, farm)
        template = RecurringExpenseTemplate.objects.create(
            farm=farm,
            **values,
        )
        return Response(
            serialize_recurring_expense_template(template),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _validate(data, farm, existing=None):
        values = {}
        partial = existing is not None

        if not partial or "categoryId" in data:
            category_id = data.get("categoryId")
            if category_id in (None, ""):
                raise ApiError(
                    "Category is required.",
                    status.HTTP_400_BAD_REQUEST,
                    "categoryId",
                )
            values["category"] = scoped_get(
                ExpenseCategoryRecord,
                farm,
                category_id,
                "The selected expense category does not exist.",
                "categoryId",
            )

        if not partial or "amount" in data:
            amount = parse_body_decimal(
                data,
                "amount",
                "Amount is required.",
                "Amount must be a number.",
                positive_message="Amount must be greater than zero.",
            )
            try:
                RecurringExpenseTemplate._meta.get_field(
                    "amount"
                ).run_validators(amount)
            except ValidationError as exc:
                raise ApiError(
                    "Amount must fit within 10 integer digits and 4 decimal places.",
                    status.HTTP_400_BAD_REQUEST,
                    "amount",
                ) from exc
            values["amount"] = amount

        if not partial or "frequency" in data:
            frequency = data.get("frequency")
            if frequency not in RecurringExpenseFrequency.values:
                raise ApiError(
                    "Frequency must be daily, weekly, monthly, or yearly.",
                    status.HTTP_400_BAD_REQUEST,
                    "frequency",
                )
            values["frequency"] = frequency

        if not partial or "nextDueDate" in data:
            values["next_due_date"] = parse_body_date(
                data,
                "nextDueDate",
                "Next due date is required.",
                "Next due date must be a valid calendar date.",
            )

        if "paused" in data:
            if not isinstance(data["paused"], bool):
                raise ApiError(
                    "Paused must be a boolean.",
                    status.HTTP_400_BAD_REQUEST,
                    "paused",
                )
            values["paused"] = data["paused"]
        elif not partial:
            values["paused"] = False

        return values


class RecurringExpenseTemplateDetailView(APIView):
    def get(self, request, template_id):
        farm = get_farm(request.user)
        template = scoped_get(
            RecurringExpenseTemplate,
            farm,
            template_id,
            "That recurring expense template no longer exists.",
        )
        return Response(serialize_recurring_expense_template(template))

    def put(self, request, template_id):
        return self._update(request, template_id)

    def patch(self, request, template_id):
        return self._update(request, template_id)

    @staticmethod
    def _update(request, template_id):
        farm = get_farm(request.user)
        template = scoped_get(
            RecurringExpenseTemplate,
            farm,
            template_id,
            "That recurring expense template no longer exists.",
        )
        values = RecurringExpenseTemplateListView._validate(
            request.data, farm, existing=template
        )
        with transaction.atomic():
            template = RecurringExpenseTemplate.objects.select_for_update().get(
                pk=template.pk
            )
            new_date = values.get("next_due_date")
            if (
                new_date is not None
                and new_date < template.next_due_date
                and Notification.objects.filter(
                    recurring_expense_template=template,
                    occurrence_date__gte=new_date,
                ).exists()
            ):
                raise ApiError(
                    "Next due date is earlier than a reminder that was "
                    "already sent. Reload the template and try again.",
                    status.HTTP_409_CONFLICT,
                    "nextDueDate",
                )
            for field, value in values.items():
                setattr(template, field, value)
            template.save(update_fields=[*values.keys(), "updated_at"])
        template.refresh_from_db()
        return Response(serialize_recurring_expense_template(template))

    def delete(self, request, template_id):
        farm = get_farm(request.user)
        template = scoped_get(
            RecurringExpenseTemplate,
            farm,
            template_id,
            "That recurring expense template no longer exists.",
        )
        template.delete()
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


class ExpenseReverseView(APIView):
    def post(self, request, expense_id):
        farm = get_farm(request.user)
        try:
            reversal = reverse_expense(farm, expense_id)
        except ReversalError as exc:
            raise ApiError(exc.message, exc.status_code)
        return Response(
            serialize_expense(reversal), status=status.HTTP_201_CREATED
        )


class ImportPreviewView(APIView):
    def post(self, request):
        farm = get_farm(request.user)
        raw_type = request.data.get("entityType")
        entity_type = (
            str(raw_type).strip().lower() if raw_type is not None else ""
        )
        entity_type = {
            "expense": "expenses",
            "inventory-movements": "inventory_movements",
            "inventorymovements": "inventory_movements",
        }.get(entity_type, entity_type)
        if not entity_type:
            raise ApiError(
                "Entity type is required.",
                status.HTTP_400_BAD_REQUEST,
                "entityType",
            )
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise ApiError(
                "Unsupported import type. Use expenses or "
                "inventory_movements.",
                status.HTTP_400_BAD_REQUEST,
                "entityType",
            )
        upload = request.FILES.get("file")
        if upload is None or not getattr(upload, "name", ""):
            raise ApiError(
                "Import file is required.",
                status.HTTP_400_BAD_REQUEST,
                "file",
            )
        try:
            payload = preview_import(farm, entity_type, upload)
        except ImportFileError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "file"
            )
        return Response(payload)


class ImportCommitView(APIView):
    def post(self, request):
        farm = get_farm(request.user)
        token = request.data.get("token") or request.data.get(
            "previewToken"
        )
        confirmed = request.data.get("confirmedRows")
        if confirmed is None:
            confirmed = request.data.get("confirmed")
        try:
            payload = commit_import(
                farm,
                request.user,
                token,
                confirmed,
                request.data.get("corrections"),
            )
        except ImportCommitError as exc:
            raise ApiError(str(exc), exc.status_code, exc.field)
        return Response(payload, status=status.HTTP_201_CREATED)


class BudgetListView(APIView):
    def get(self, request):
        farm = get_farm(request.user)
        budgets = farm.budgets.all()
        cycle_id = request.query_params.get("cycle")
        if cycle_id:
            budgets = budgets.filter(cycle_id=cycle_id)
        category = request.query_params.get("category")
        if category:
            budgets = budgets.filter(category=category)
        return Response([serialize_budget(budget) for budget in budgets])

    def post(self, request):
        farm = get_farm(request.user)
        values = self._validate(request.data, farm)
        budget = Budget.objects.create(farm=farm, **values)
        return Response(
            serialize_budget(budget), status=status.HTTP_201_CREATED
        )

    @staticmethod
    def _validate(data, farm):
        try:
            amount = parse_decimal(
                data.get("amount"),
                "amount",
                "Amount is required.",
                "Amount must be a number.",
                positive_message="Amount must be greater than zero.",
            )
        except ValueError as exc:
            raise ApiError(
                str(exc), status.HTTP_400_BAD_REQUEST, "amount"
            )

        category = None
        raw_category = data.get("category")
        if raw_category not in (None, ""):
            category = str(raw_category).strip()
            if category not in ExpenseCategory.values:
                raise ApiError(
                    "Category must be one of: inputs, labour, equipment, "
                    "overhead, other.",
                    status.HTTP_400_BAD_REQUEST,
                    "category",
                )

        cycle = None
        cycle_id = data.get("cycleId")
        if cycle_id not in (None, ""):
            try:
                cycle = CropCycle.objects.get(farm=farm, pk=cycle_id)
            except (CropCycle.DoesNotExist, ValueError, ValidationError):
                raise ApiError(
                    "The selected crop cycle does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    "cycleId",
                )

        period_start = parse_optional_body_date(
            data,
            "periodStart",
            "Period start must be a valid calendar date.",
        )
        period_end = parse_optional_body_date(
            data,
            "periodEnd",
            "Period end must be a valid calendar date.",
        )
        if (
            period_start is not None
            and period_end is not None
            and period_end < period_start
        ):
            raise ApiError(
                "Period end cannot be before the period start.",
                status.HTTP_400_BAD_REQUEST,
                "periodEnd",
            )

        return {
            "cycle": cycle,
            "category": category,
            "amount": amount,
            "period_start": period_start,
            "period_end": period_end,
        }


class BudgetDetailView(APIView):
    def get(self, request, budget_id):
        farm = get_farm(request.user)
        budget = scoped_get(
            Budget, farm, budget_id, "That budget no longer exists."
        )
        return Response(serialize_budget(budget))

    def put(self, request, budget_id):
        farm = get_farm(request.user)
        budget = scoped_get(
            Budget, farm, budget_id, "That budget no longer exists."
        )
        values = BudgetListView._validate(request.data, farm)
        budget.cycle = values["cycle"]
        budget.category = values["category"]
        budget.amount = values["amount"]
        budget.period_start = values["period_start"]
        budget.period_end = values["period_end"]
        budget.save()
        return Response(serialize_budget(budget))

    def delete(self, request, budget_id):
        farm = get_farm(request.user)
        budget = scoped_get(
            Budget, farm, budget_id, "That budget no longer exists."
        )
        budget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        values = validate_payment(request.data, farm)
        payment = Payment.objects.create(farm=farm, **values)
        return Response(
            serialize_payment(payment),
            status=status.HTTP_201_CREATED,
        )


class PaymentDetailView(APIView):
    def get(self, request, payment_id):
        farm = get_farm(request.user)
        return Response(
            serialize_payment(self._payment(farm, payment_id))
        )

    def put(self, request, payment_id):
        farm = get_farm(request.user)
        payment = self._payment(farm, payment_id)
        self._reject_change(payment)

    def patch(self, request, payment_id):
        farm = get_farm(request.user)
        payment = self._payment(farm, payment_id)
        self._reject_change(payment)

    def delete(self, request, payment_id):
        farm = get_farm(request.user)
        payment = self._payment(farm, payment_id)
        self._reject_change(payment, "deleted")

    @staticmethod
    def _reject_change(payment, action="edited"):
        raise ApiError(
            f"Recorded payments cannot be {action}. "
            "Reverse the payment instead.",
            status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def _payment(farm, payment_id):
        return scoped_get(
            Payment, farm, payment_id, "That payment no longer exists."
        )


class PaymentReverseView(APIView):
    def post(self, request, payment_id):
        farm = get_farm(request.user)
        try:
            reversal = reverse_payment(farm, payment_id)
        except ReversalError as exc:
            raise ApiError(exc.message, exc.status_code)
        return Response(
            serialize_payment(reversal), status=status.HTTP_201_CREATED
        )


def validate_payment(data, farm):
    payment_type = str(data.get("type") or "").strip()
    if payment_type not in PaymentType.values:
        raise ApiError(
            "Payment type must be either received or paid.",
            status.HTTP_400_BAD_REQUEST,
            "type",
        )
    amount = parse_body_decimal(
        data,
        "amount",
        "Amount is required.",
        "Amount must be a number.",
        positive_message="Amount must be greater than zero.",
    )
    try:
        Payment._meta.get_field("amount").run_validators(amount)
    except ValidationError as exc:
        raise ApiError(
            "Amount must fit within 10 integer digits and 4 decimal "
            "places.",
            status.HTTP_400_BAD_REQUEST,
            "amount",
        ) from exc
    payment_date = parse_body_date(
        data,
        "date",
        "Date is required.",
        "Date must be a valid calendar date.",
    )
    if payment_date > timezone.localdate():
        raise ApiError(
            "Date cannot be in the future.",
            status.HTTP_400_BAD_REQUEST,
            "date",
        )

    linked_expense = None
    expense_id = data.get("linkedExpenseId")
    if expense_id not in (None, ""):
        try:
            linked_expense = Expense.objects.get(farm=farm, pk=expense_id)
        except (Expense.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That expense no longer exists.",
                status.HTTP_400_BAD_REQUEST,
                "linkedExpenseId",
            )

    linked_sale = None
    sale_id = data.get("linkedSaleId")
    if sale_id not in (None, ""):
        try:
            linked_sale = Sale.objects.get(farm=farm, pk=sale_id)
        except (Sale.DoesNotExist, ValueError, ValidationError):
            raise ApiError(
                "That sale no longer exists.",
                status.HTTP_400_BAD_REQUEST,
                "linkedSaleId",
            )

    if linked_expense is not None and linked_sale is not None:
        raise ApiError(
            "A payment cannot link to both a sale and an expense.",
            status.HTTP_400_BAD_REQUEST,
            "linkedSaleId",
        )
    if linked_sale is not None and payment_type != PaymentType.RECEIVED:
        raise ApiError(
            "Only received payments can link to a sale.",
            status.HTTP_400_BAD_REQUEST,
            "linkedSaleId",
        )
    if linked_expense is not None and payment_type != PaymentType.PAID:
        raise ApiError(
            "Only paid payments can link to an expense.",
            status.HTTP_400_BAD_REQUEST,
            "linkedExpenseId",
        )

    reference = optional_text(data, "reference")
    reference_max_length = Payment._meta.get_field("reference").max_length
    if len(reference) > reference_max_length:
        raise ApiError(
            f"Reference must be {reference_max_length} characters or fewer.",
            status.HTTP_400_BAD_REQUEST,
            "reference",
        )

    return {
        "type": payment_type,
        "amount": amount,
        "date": payment_date,
        "linked_expense": linked_expense,
        "linked_sale": linked_sale,
        "reference": reference or None,
    }

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


def _unit_data(unit):
    return UnitData(unit.pk, unit.name, unit.base_measure)


def _conversion_rule_data(farm, from_unit, to_unit):
    rules = UnitConversion.objects.filter(farm=farm).filter(
        Q(from_unit=from_unit, to_unit=to_unit)
        | Q(from_unit=to_unit, to_unit=from_unit)
    )
    return [
        ConversionRuleData(
            rule.from_unit_id,
            rule.to_unit_id,
            rule.factor,
        )
        for rule in rules
    ]


def _convert_quantity_between_units(farm, quantity, from_unit, to_unit):
    source_data = _unit_data(from_unit)
    target_data = _unit_data(to_unit)
    rules = (
        []
        if from_unit.pk == to_unit.pk
        else _conversion_rule_data(farm, from_unit, to_unit)
    )
    try:
        return convert_quantity(quantity, source_data, target_data, rules)
    except UnitConversionError as exc:
        raise ApiError(str(exc), status.HTTP_400_BAD_REQUEST)


def aggregate_harvest_quantity_for_cycle(farm, cycle, through_date=None):
    harvests = Harvest.objects.filter(farm=farm, cycle=cycle)
    if through_date is not None:
        harvests = harvests.filter(date__lte=through_date)
    harvests = list(harvests.select_related("unit"))
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


class CounterpartyListView(APIView):
    model = None
    serializer = None
    noun = None

    def get(self, request):
        farm = get_farm(request.user)
        return Response(
            [
                self.serializer(counterparty)
                for counterparty in self.model.objects.filter(farm=farm)
            ]
        )

    def post(self, request):
        farm = get_farm(request.user)
        name = require_name(request.data, "name", self.noun)
        values = self._optional_values(request.data)
        counterparty = self.model.objects.create(
            farm=farm, name=name, **values
        )
        return Response(
            self.serializer(counterparty),
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _optional_values(data):
        values = {}
        for api_field, model_field in COUNTERPARTY_OPTIONAL_FIELDS:
            if api_field not in data:
                continue
            value = validate_counterparty_length(
                optional_text(data, api_field), api_field
            )
            if api_field == "email" and value:
                try:
                    validate_email(value)
                except ValidationError:
                    raise ApiError(
                        "Enter a valid email address.",
                        status.HTTP_400_BAD_REQUEST,
                        "email",
                    )
            values[model_field] = value
        return values


class CounterpartyDetailView(APIView):
    model = None
    serializer = None
    noun = None
    id_kwarg = None

    def get(self, request, **kwargs):
        counterparty = self._get(request, kwargs)
        return Response(self.serializer(counterparty))

    def put(self, request, **kwargs):
        return self._update(request, kwargs)

    def patch(self, request, **kwargs):
        return self._update(request, kwargs)

    def delete(self, request, **kwargs):
        counterparty = self._get(request, kwargs)
        self._validate_delete(counterparty)
        try:
            counterparty.delete()
        except ProtectedError:
            raise ApiError(
                f"This {self.noun} is linked to existing records and "
                "cannot be deleted.",
                status.HTTP_409_CONFLICT,
                "id",
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _validate_delete(self, counterparty):
        pass

    def _get(self, request, kwargs):
        farm = get_farm(request.user)
        return scoped_get(
            self.model,
            farm,
            kwargs[self.id_kwarg],
            f"That {self.noun} no longer exists.",
        )

    def _update(self, request, kwargs):
        counterparty = self._get(request, kwargs)
        changed = False
        if "name" in request.data:
            counterparty.name = require_name(
                request.data, "name", self.noun
            )
            changed = True
        for model_field, value in CounterpartyListView._optional_values(
            request.data
        ).items():
            setattr(counterparty, model_field, value)
            changed = True
        if changed:
            counterparty.save()
        return Response(self.serializer(counterparty))


class SupplierListView(CounterpartyListView):
    model = Supplier
    serializer = staticmethod(serialize_supplier)
    noun = "Supplier"


class SupplierDetailView(CounterpartyDetailView):
    model = Supplier
    serializer = staticmethod(serialize_supplier)
    noun = "supplier"
    id_kwarg = "supplier_id"

    def _validate_delete(self, supplier):
        if supplier.expenses.exists():
            raise ApiError(
                "This supplier is linked to expenses and cannot be deleted.",
                status.HTTP_409_CONFLICT,
                "id",
            )


class CustomerListView(CounterpartyListView):
    model = Customer
    serializer = staticmethod(serialize_customer)
    noun = "Customer"


class CustomerDetailView(CounterpartyDetailView):
    model = Customer
    serializer = staticmethod(serialize_customer)
    noun = "customer"
    id_kwarg = "customer_id"


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


class ProfitabilityReportView(APIView):
    def get(self, request):
        from .reporting import aggregate_profitability

        farm = get_farm(request.user)
        self._validate_farm_param(farm, request)
        return Response(
            aggregate_profitability(
                farm, request.query_params.get("group_by")
            )
        )

    @staticmethod
    def _validate_farm_param(farm, request):
        for key in ("farm", "farmId"):
            value = request.query_params.get(key)
            if value in (None, ""):
                continue
            if str(value) != str(farm.id):
                raise ApiError(
                    "That farm does not exist.",
                    status.HTTP_404_NOT_FOUND,
                    key,
                )


class ReportExportView(APIView):
    format_kwarg = None

    def get(self, request, report_name):
        farm = get_farm(request.user)
        file_format = request.query_params.get("exportFormat")
        if file_format not in ("csv", "xlsx", "pdf"):
            raise ApiError(
                "exportFormat must be csv, xlsx or pdf.",
                status.HTTP_400_BAD_REQUEST,
                "exportFormat",
            )
        if report_name == "profitability":
            ProfitabilityReportView._validate_farm_param(farm, request)
        payload = report_payload(
            report_name, farm, request.query_params
        )
        return render_report_export(
            report_name,
            payload,
            file_format,
            request.query_params,
            farm=farm,
        )


class BudgetVsActualReportView(APIView):
    def get(self, request):
        from .budget_reports import budget_vs_actual_report

        farm = get_farm(request.user)
        return Response(
            budget_vs_actual_report(farm, request.query_params)
        )


class DashboardView(APIView):
    def get(self, request):
        from .dashboard import dashboard_for_request

        farm = get_farm(request.user)
        return Response(dashboard_for_request(farm, request.query_params))


class OperationalReportView(APIView):
    report_name = ""

    def get(self, request):
        from . import operational_reports

        farm = get_farm(request.user)
        report = getattr(operational_reports, self.report_name)
        return Response(report(farm, request.query_params))


class ActivityStatusReportView(OperationalReportView):
    report_name = "activity_status_report"


class InventoryReportView(OperationalReportView):
    report_name = "inventory_report"


class LabourUsageReportView(OperationalReportView):
    report_name = "labour_usage_report"


class EquipmentUsageReportView(OperationalReportView):
    report_name = "equipment_usage_report"


DEFAULT_NOTIFICATION_PAGE_SIZE = 20
MAX_NOTIFICATION_PAGE_SIZE = 100


def notification_for_user(user, notification_id):
    try:
        return Notification.objects.get(user=user, pk=notification_id)
    except (Notification.DoesNotExist, ValueError, ValidationError):
        raise ApiError(
            "That notification no longer exists.",
            status.HTTP_404_NOT_FOUND,
            "id",
        )


def notification_page_param(request, key, default, maximum=None):
    raw = request.query_params.get(key)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(
            f"{key} must be a positive whole number.",
            status.HTTP_400_BAD_REQUEST,
            key,
        )
    if value < 1 or (maximum is not None and value > maximum):
        limit = f" between 1 and {maximum}" if maximum is not None else ""
        raise ApiError(
            f"{key} must be a positive whole number{limit}.",
            status.HTTP_400_BAD_REQUEST,
            key,
        )
    return value


class NotificationListView(APIView):
    def get(self, request):
        page_size = notification_page_param(
            request,
            "page_size",
            DEFAULT_NOTIFICATION_PAGE_SIZE,
            MAX_NOTIFICATION_PAGE_SIZE,
        )
        page_number = notification_page_param(request, "page", 1)
        notifications = Notification.objects.filter(user=request.user)
        unread_count = notifications.filter(read=False).count()
        paginator = Paginator(notifications, page_size)
        try:
            page = paginator.page(page_number)
        except EmptyPage:
            raise ApiError(
                "That page does not exist.",
                status.HTTP_404_NOT_FOUND,
                "page",
            )
        return Response(
            {
                "count": paginator.count,
                "unreadCount": unread_count,
                "page": page.number,
                "pageSize": page_size,
                "totalPages": paginator.num_pages,
                "nextPage": (
                    page.next_page_number() if page.has_next() else None
                ),
                "previousPage": (
                    page.previous_page_number()
                    if page.has_previous()
                    else None
                ),
                "results": [
                    serialize_notification(notification)
                    for notification in page.object_list
                ],
            }
        )


class NotificationDetailView(APIView):
    def get(self, request, notification_id):
        notification = notification_for_user(
            request.user, notification_id
        )
        return Response(serialize_notification(notification))


class NotificationMarkReadView(APIView):
    def post(self, request, notification_id):
        return self._mark_read(request, notification_id)

    def put(self, request, notification_id):
        return self._mark_read(request, notification_id)

    def patch(self, request, notification_id):
        return self._mark_read(request, notification_id)

    @staticmethod
    def _mark_read(request, notification_id):
        notification = notification_for_user(
            request.user, notification_id
        )
        if not notification.read:
            notification.read = True
            notification.save(update_fields=["read", "updated_at"])
        return Response(serialize_notification(notification))


class NotificationMarkAllReadView(APIView):
    def post(self, request):
        return self._mark_all_read(request)

    def put(self, request):
        return self._mark_all_read(request)

    @staticmethod
    def _mark_all_read(request):
        updated = Notification.objects.filter(
            user=request.user, read=False
        ).update(read=True, updated_at=timezone.now())
        return Response({"updated": updated, "unreadCount": 0})


class NotificationUnreadCountView(APIView):
    def get(self, request):
        count = Notification.objects.filter(
            user=request.user, read=False
        ).count()
        return Response({"unreadCount": count})
