import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    OWNER = "owner", "owner"
    MANAGER = "manager", "manager"
    WORKER = "worker", "worker"


class BaseMeasure(models.TextChoices):
    MASS = "mass", "mass"
    VOLUME = "volume", "volume"
    COUNT = "count", "count"


class CycleStatus(models.TextChoices):
    OPEN = "open", "open"
    CLOSED = "closed", "closed"


class ActivityCategory(models.TextChoices):
    LAND_PREPARATION = "land preparation", "land preparation"
    PLANTING = "planting", "planting"
    FERTILIZING = "fertilizing", "fertilizing"
    SPRAYING = "spraying", "spraying"
    HARVESTING = "harvesting", "harvesting"
    CUSTOM = "custom", "custom"


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

    def __str__(self):
        return self.email


class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="farm"
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
        Crop, on_delete=models.CASCADE, related_name="crop_cycles"
    )
    variety = models.ForeignKey(
        Variety, on_delete=models.CASCADE, related_name="crop_cycles"
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
    category = models.CharField(
        max_length=32, choices=ActivityCategory.choices
    )
    standard = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at", "id"]


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

    def current_quantity(self):
        total = sum(
            (
                movement.quantity
                if movement.type != MovementType.USAGE
                else -movement.quantity
            )
            for movement in self.movements.all()
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
