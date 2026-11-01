import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Role(models.TextChoices):
    OWNER = "owner", "owner"
    MANAGER = "manager", "manager"
    WORKER = "worker", "worker"


class NotificationType(models.TextChoices):
    INFO = "info", "info"
    WARNING = "warning", "warning"
    ALERT = "alert", "alert"


class BaseMeasure(models.TextChoices):
    MASS = "mass", "mass"
    VOLUME = "volume", "volume"
    COUNT = "count", "count"


class CycleStatus(models.TextChoices):
    OPEN = "open", "open"
    CLOSED = "closed", "closed"


class CycleType(models.TextChoices):
    ANNUAL = "annual", "annual"
    PERENNIAL = "perennial", "perennial"


class ActivityCategory(models.TextChoices):
    LAND_PREPARATION = "land preparation", "land preparation"
    PLANTING = "planting", "planting"
    FERTILIZING = "fertilizing", "fertilizing"
    SPRAYING = "spraying", "spraying"
    HARVESTING = "harvesting", "harvesting"


class ActivityStatus(models.TextChoices):
    PLANNED = "planned", "planned"
    IN_PROGRESS = "in_progress", "in progress"
    COMPLETED = "completed", "completed"
    OVERDUE = "overdue", "overdue"


class MovementType(models.TextChoices):
    PURCHASE = "purchase", "purchase"
    USAGE = "usage", "usage"
    ADJUSTMENT = "adjustment", "adjustment"


class ExpenseCategory(models.TextChoices):
    INPUTS = "inputs", "inputs"
    LABOUR = "labour", "labour"
    EQUIPMENT = "equipment", "equipment"
    OVERHEAD = "overhead", "overhead"
    OTHER = "other", "other"


class ExpenseStatus(models.TextChoices):
    DRAFT = "draft", "draft"
    POSTED = "posted", "posted"


class PaymentType(models.TextChoices):
    RECEIVED = "received", "received"
    PAID = "paid", "paid"


class AllocationBasis(models.TextChoices):
    PER_HECTARE = "per_hectare", "per hectare"
    PER_CYCLE_SHARE = "per_cycle_share", "per cycle share"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.OWNER
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values),
                name="api_user_role_valid",
            )
        ]

    def __str__(self):
        return self.email


class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="farm"
    )
    members = models.ManyToManyField(
        User, blank=True, related_name="member_farms"
    )
    name = models.CharField(max_length=255)
    reporting_currency = models.CharField(max_length=3)

    def __str__(self):
        return self.name


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Season(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="seasons"
    )
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    year = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="uniq_season_farm_name",
            )
        ]


class ReportingPeriod(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="reporting_periods"
    )
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    year = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name"],
                name="uniq_report_period_farm_name",
            )
        ]


class Field(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="fields"
    )
    name = models.CharField(max_length=255)
    area = models.DecimalField(max_digits=14, decimal_places=4)
    notes = models.TextField(blank=True, default="")
    polygon = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class Crop(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="crops"
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "farm",
                name="uniq_crop_farm_name_ci",
            )
        ]


class Variety(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="varieties"
    )
    crop = models.ForeignKey(
        Crop, on_delete=models.CASCADE, related_name="varieties"
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["created_at", "id"]


class Unit(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="units"
    )
    name = models.CharField(max_length=255)
    base_measure = models.CharField(max_length=20, choices=BaseMeasure.choices)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "farm",
                name="uniq_unit_farm_name_ci",
            )
        ]


class UnitConversion(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="conversions"
    )
    from_unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name="conversions_from"
    )
    to_unit = models.ForeignKey(
        Unit, on_delete=models.CASCADE, related_name="conversions_to"
    )
    factor = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        ordering = ["created_at", "id"]


class CropCycle(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="crop_cycles"
    )
    field = models.ForeignKey(
        Field, on_delete=models.CASCADE, related_name="crop_cycles"
    )
    crop = models.ForeignKey(
        Crop, on_delete=models.RESTRICT, related_name="crop_cycles"
    )
    variety = models.ForeignKey(
        Variety,
        on_delete=models.RESTRICT,
        related_name="crop_cycles",
        null=True,
        blank=True,
    )
    cycle_type = models.CharField(
        max_length=16,
        choices=CycleType.choices,
        null=True,
        blank=True,
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=CycleStatus.choices, default=CycleStatus.OPEN
    )
    expected_yield = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )
    expected_price = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True
    )

    class Meta:
        ordering = ["created_at", "id"]


class ActivityType(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="activity_types"
    )
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=32)
    standard = models.BooleanField(default=False)
    default_inputs = models.JSONField(default=list)
    default_labour_hours = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        validators=[MinValueValidator(0)],
    )
    default_equipment = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                "farm",
                name="uniq_activity_type_farm_name_ci",
            ),
            models.CheckConstraint(
                condition=models.Q(default_labour_hours__gte=0),
                name="activity_type_labour_hours_nonnegative",
            ),
        ]


class Activity(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="activities"
    )
    cycle = models.ForeignKey(
        CropCycle, on_delete=models.CASCADE, related_name="activities"
    )
    type = models.ForeignKey(
        ActivityType, on_delete=models.PROTECT, related_name="activities"
    )
    assignees = models.ManyToManyField(
        User, blank=True, related_name="assigned_activities"
    )
    planned_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=ActivityStatus.choices,
        default=ActivityStatus.PLANNED,
    )
    description = models.TextField(blank=True, default="")
    labour_hours = models.DecimalField(
        max_digits=14, decimal_places=4, default=0
    )
    equipment = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["created_at", "id"]


class ActivityInputNeed(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity = models.ForeignKey(
        Activity, on_delete=models.CASCADE, related_name="input_needs"
    )
    item_name = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        ordering = ["id"]


class InventoryItem(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="inventory_items"
    )
    name = models.CharField(max_length=255)
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="inventory_items"
    )
    reorder_level = models.DecimalField(
        max_digits=14, decimal_places=4, default=0
    )

    class Meta:
        ordering = ["created_at", "id"]

    def current_quantity(self, as_of_date=None):
        movements = self.movements.all()
        if as_of_date is not None:
            movements = (
                movement
                for movement in movements
                if movement.date is not None and movement.date <= as_of_date
            )
        total = sum(
            (
                movement.quantity
                if movement.type != MovementType.USAGE
                else -movement.quantity
            )
            for movement in movements
        )
        return total


class StockMovement(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="stock_movements"
    )
    item = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name="movements"
    )
    type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["created_at", "id"]


class Supplier(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="suppliers"
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["name", "id"]


class Customer(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="customers"
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ["created_at", "id"]


class Expense(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="expenses"
    )
    cycle = models.ForeignKey(
        CropCycle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )
    category = models.CharField(
        max_length=32, choices=ExpenseCategory.choices
    )
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    date = models.DateField()
    supplier = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=ExpenseStatus.choices,
        default=ExpenseStatus.DRAFT,
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["created_at", "id"]


class Budget(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="budgets"
    )
    cycle = models.ForeignKey(
        CropCycle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="budgets",
    )
    category = models.CharField(
        max_length=32,
        choices=ExpenseCategory.choices,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="budget_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(period_start__isnull=True)
                    | models.Q(period_end__isnull=True)
                    | models.Q(period_end__gte=models.F("period_start"))
                ),
                name="budget_period_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= 0:
            errors["amount"] = "Amount must be greater than zero."
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            errors["period_end"] = (
                "period_end must not be earlier than period_start."
            )
        if (
            self.cycle_id is not None
            and self.farm_id is not None
            and self.cycle.farm_id != self.farm_id
        ):
            errors["cycle"] = "The crop cycle must belong to the same farm."
        if errors:
            raise ValidationError(errors)


class AllocationRule(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="allocation_rules"
    )
    name = models.CharField(max_length=255)
    basis = models.CharField(max_length=32, choices=AllocationBasis.choices)
    parameters = models.JSONField(default=dict, blank=True)
    active_from = models.DateField(null=True, blank=True)
    active_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(active_from__isnull=True)
                    | models.Q(active_to__isnull=True)
                    | models.Q(active_to__gte=models.F("active_from"))
                ),
                name="allocation_rule_active_period_valid",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.active_from is not None
            and self.active_to is not None
            and self.active_to < self.active_from
        ):
            raise ValidationError(
                {
                    "active_to": (
                        "active_to must not be earlier than active_from."
                    )
                }
            )


class Attachment(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="attachments/%Y/%m/")
    name = models.CharField(max_length=255)


class Harvest(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="harvests"
    )
    cycle = models.ForeignKey(
        CropCycle, on_delete=models.CASCADE, related_name="harvests"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey(
        Unit, on_delete=models.PROTECT, related_name="harvests"
    )
    date = models.DateField()

    class Meta:
        ordering = ["created_at", "id"]


class Sale(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="sales"
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="sales"
    )
    harvest = models.ForeignKey(
        Harvest, on_delete=models.CASCADE, related_name="sales"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    date = models.DateField()
    revenue = models.DecimalField(max_digits=18, decimal_places=4)

    class Meta:
        ordering = ["created_at", "id"]


class Payment(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="payments"
    )
    type = models.CharField(max_length=20, choices=PaymentType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=4)
    date = models.DateField()
    linked_expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    linked_sale = models.ForeignKey(
        Sale,
        on_delete=models.SET_NULL,
        related_name="payments",
        null=True,
        blank=True,
    )
    reference = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["created_at", "id"]


class ImportPreview(models.Model):
    """Server-side state for a validated import preview.

    The token is single-use: a successful commit records ``consumed_at`` so
    replaying the same preview cannot create records twice.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="import_previews"
    )
    entity_type = models.CharField(max_length=32)
    columns = models.JSONField(default=dict)
    rows = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]


class ImportCommit(models.Model):
    """Minimal audit record for a confirmed import commit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm, on_delete=models.CASCADE, related_name="import_commits"
    )
    actor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="import_commits"
    )
    preview_token = models.UUIDField()
    entity_type = models.CharField(max_length=32)
    entity_counts = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]


class Notification(TimestampedModel):
    """An in-app notification addressed to a single user."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
    )
    message = models.TextField()
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(
                fields=["user", "read", "-created_at"],
                name="notif_user_read_created_idx",
            )
        ]

    def __str__(self):
        return f"{self.type}: {self.message[:50]}"

    @property
    def is_read(self):
        return self.read
