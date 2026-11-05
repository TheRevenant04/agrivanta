import pytest
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from api.models import (
    Activity,
    ActivityStatus,
    ActivityType,
    Budget,
    CropCycle,
    Crop,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Farm,
    Field,
    InventoryItem,
    MovementType,
    Notification,
    NotificationType,
    StockMovement,
    Unit,
    User,
    Variety,
)
from api.tasks import (
    check_overdue_activities,
    check_low_stock,
    check_budget_overruns,
)


@pytest.fixture
def farm_with_owner(db):
    """Create a farm with an owner."""
    owner = User.objects.create_user(
        email="owner@test.com", password="test123"
    )
    farm = Farm.objects.create(
        owner=owner, name="Test Farm", reporting_currency="USD"
    )
    return farm, owner


@pytest.fixture
def field_and_crop(db, farm_with_owner):
    """Create field and crop for the farm."""
    farm, owner = farm_with_owner
    field = Field.objects.create(
        farm=farm, name="North Field", area=Decimal("10.5")
    )
    crop = Crop.objects.create(farm=farm, name="Wheat")
    variety = Variety.objects.create(crop=crop, farm=farm, name="Winter Wheat")
    return field, crop, variety, farm, owner


@pytest.fixture
def crop_cycle(db, field_and_crop):
    """Create an active crop cycle."""
    field, crop, variety, farm, owner = field_and_crop
    cycle = CropCycle.objects.create(
        farm=farm,
        field=field,
        crop=crop,
        variety=variety,
        cycle_type="annual",
        start_date=date.today() - timedelta(days=30),
    )
    return cycle, farm, owner


class TestOverdueActivities:
    """Test check_overdue_activities task."""

    def test_creates_notification_for_overdue_planned_activity(
        self, db, crop_cycle
    ):
        """Notification created for overdue PLANNED activity."""
        cycle, farm, owner = crop_cycle
        activity_type = ActivityType.objects.create(
            farm=farm, name="Planting", category="planting", standard=False
        )
        overdue_date = date.today() - timedelta(days=5)
        activity = Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=overdue_date,
            status=ActivityStatus.PLANNED,
        )

        check_overdue_activities()

        notification = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).first()
        assert notification is not None
        assert "overdue" in notification.message.lower()
        assert activity_type.name in notification.message

    def test_creates_notification_for_overdue_in_progress_activity(
        self, db, crop_cycle
    ):
        """Notification created for overdue IN_PROGRESS activity."""
        cycle, farm, owner = crop_cycle
        activity_type = ActivityType.objects.create(
            farm=farm, name="Harvesting", category="harvesting", standard=False
        )
        overdue_date = date.today() - timedelta(days=1)
        activity = Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=overdue_date,
            status=ActivityStatus.IN_PROGRESS,
        )

        check_overdue_activities()

        notification = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).first()
        assert notification is not None
        assert "overdue" in notification.message.lower()

    def test_no_notification_for_future_activity(self, db, crop_cycle):
        """No notification for future PLANNED activity."""
        cycle, farm, owner = crop_cycle
        activity_type = ActivityType.objects.create(
            farm=farm, name="Planting", category="planting", standard=False
        )
        future_date = date.today() + timedelta(days=5)
        Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=future_date,
            status=ActivityStatus.PLANNED,
        )

        check_overdue_activities()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_no_notification_for_completed_activity(self, db, crop_cycle):
        """No notification for COMPLETED activity."""
        cycle, farm, owner = crop_cycle
        activity_type = ActivityType.objects.create(
            farm=farm, name="Planting", category="planting", standard=False
        )
        overdue_date = date.today() - timedelta(days=5)
        Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=overdue_date,
            status=ActivityStatus.COMPLETED,
        )

        check_overdue_activities()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_idempotent_no_duplicate_notifications(self, db, crop_cycle):
        """Running task twice doesn't create duplicate notifications."""
        cycle, farm, owner = crop_cycle
        activity_type = ActivityType.objects.create(
            farm=farm, name="Planting", category="planting", standard=False
        )
        overdue_date = date.today() - timedelta(days=5)
        Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type,
            planned_date=overdue_date,
            status=ActivityStatus.PLANNED,
        )

        check_overdue_activities()
        initial_count = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).count()
        assert initial_count == 1

        check_overdue_activities()
        final_count = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).count()
        assert final_count == 1

    def test_multiple_overdue_activities(self, db, crop_cycle):
        """Creates notifications for multiple overdue activities."""
        cycle, farm, owner = crop_cycle
        activity_type1 = ActivityType.objects.create(
            farm=farm, name="Planting", category="planting", standard=False
        )
        activity_type2 = ActivityType.objects.create(
            farm=farm, name="Harvesting", category="harvesting", standard=False
        )
        overdue_date = date.today() - timedelta(days=5)

        Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type1,
            planned_date=overdue_date,
            status=ActivityStatus.PLANNED,
        )
        Activity.objects.create(
            farm=farm,
            cycle=cycle,
            type=activity_type2,
            planned_date=overdue_date,
            status=ActivityStatus.IN_PROGRESS,
        )

        check_overdue_activities()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 2


class TestLowStockNotifications:
    """Test check_low_stock task."""

    @pytest.fixture
    def inventory_setup(self, db, farm_with_owner):
        """Create inventory items for testing."""
        farm, owner = farm_with_owner
        unit = Unit.objects.create(
            farm=farm, name="kg", base_measure="mass"
        )
        return farm, owner, unit

    def test_creates_notification_for_low_stock(self, db, inventory_setup):
        """Notification created for item below reorder level."""
        farm, owner, unit = inventory_setup
        item = InventoryItem.objects.create(
            farm=farm,
            name="Fertilizer A",
            unit=unit,
            reorder_level=Decimal("100"),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("50"),
            date=date.today(),
        )

        check_low_stock()

        notification = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        ).first()
        assert notification is not None
        assert "below reorder level" in notification.message.lower()
        assert "Fertilizer A" in notification.message

    def test_no_notification_for_adequate_stock(self, db, inventory_setup):
        """No notification when stock is at or above reorder level."""
        farm, owner, unit = inventory_setup
        item = InventoryItem.objects.create(
            farm=farm,
            name="Fertilizer B",
            unit=unit,
            reorder_level=Decimal("100"),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("150"),
            date=date.today(),
        )

        check_low_stock()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        )
        assert notifications.count() == 0

    def test_accounts_for_usage_movements(self, db, inventory_setup):
        """Low stock check accounts for usage decrements."""
        farm, owner, unit = inventory_setup
        item = InventoryItem.objects.create(
            farm=farm,
            name="Seeds",
            unit=unit,
            reorder_level=Decimal("50"),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("100"),
            date=date.today(),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.USAGE,
            quantity=Decimal("60"),
            date=date.today(),
        )

        check_low_stock()

        notification = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        ).first()
        assert notification is not None
        assert "Seeds" in notification.message

    def test_idempotent_no_duplicate_notifications(self, db, inventory_setup):
        """Running task twice doesn't create duplicate notifications."""
        farm, owner, unit = inventory_setup
        item = InventoryItem.objects.create(
            farm=farm,
            name="Fertilizer C",
            unit=unit,
            reorder_level=Decimal("100"),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item,
            type=MovementType.PURCHASE,
            quantity=Decimal("50"),
            date=date.today(),
        )

        check_low_stock()
        initial_count = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        ).count()
        assert initial_count == 1

        check_low_stock()
        final_count = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        ).count()
        assert final_count == 1

    def test_multiple_low_stock_items(self, db, inventory_setup):
        """Creates notifications for multiple low-stock items."""
        farm, owner, unit = inventory_setup
        item1 = InventoryItem.objects.create(
            farm=farm,
            name="Fertilizer D",
            unit=unit,
            reorder_level=Decimal("100"),
        )
        item2 = InventoryItem.objects.create(
            farm=farm,
            name="Pesticide E",
            unit=unit,
            reorder_level=Decimal("50"),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item1,
            type=MovementType.PURCHASE,
            quantity=Decimal("30"),
            date=date.today(),
        )
        StockMovement.objects.create(
            farm=farm,
            item=item2,
            type=MovementType.PURCHASE,
            quantity=Decimal("20"),
            date=date.today(),
        )

        check_low_stock()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.WARNING
        )
        assert notifications.count() == 2


class TestBudgetOverruns:
    """Test check_budget_overruns task."""

    @pytest.fixture
    def budget_setup(self, db, crop_cycle):
        """Create budget and expense setup."""
        cycle, farm, owner = crop_cycle
        return farm, owner, cycle

    def test_creates_notification_for_budget_overrun(self, db, budget_setup):
        """Notification created when actual spend exceeds budget."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("500"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("600"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notification = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).first()
        assert notification is not None
        assert "exceeded" in notification.message.lower()

    def test_no_notification_for_within_budget(self, db, budget_setup):
        """No notification when spend is within budget."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("500"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("400"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_only_counts_posted_expenses(self, db, budget_setup):
        """Only POSTED expenses count toward budget."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("200"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("300"),
            date=date.today(),
            status=ExpenseStatus.DRAFT,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_respects_budget_cycle_scope(self, db, farm_with_owner, field_and_crop):
        """Budget applies only to its specified cycle."""
        farm, owner = farm_with_owner
        field, crop, variety, _, _ = field_and_crop
        cycle1 = CropCycle.objects.create(
            farm=farm,
            field=field,
            crop=crop,
            variety=variety,
            cycle_type="annual",
            start_date=date.today() - timedelta(days=30),
        )
        cycle2 = CropCycle.objects.create(
            farm=farm,
            field=field,
            crop=crop,
            variety=variety,
            cycle_type="annual",
            start_date=date.today(),
        )

        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle1,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("200"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle2,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("300"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_respects_budget_category_scope(self, db, budget_setup):
        """Budget applies only to its specified category."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("200"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.LABOUR,
            amount=Decimal("300"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_respects_budget_period_scope(self, db, budget_setup):
        """Budget applies only to its specified period."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("200"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() - timedelta(days=5),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("300"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 0

    def test_idempotent_no_duplicate_notifications(self, db, budget_setup):
        """Running task twice doesn't create duplicate notifications."""
        farm, owner, cycle = budget_setup
        budget = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("500"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("600"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()
        initial_count = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).count()
        assert initial_count == 1

        check_budget_overruns()
        final_count = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        ).count()
        assert final_count == 1

    def test_multiple_budget_overruns(self, db, budget_setup):
        """Creates notifications for multiple budget overruns."""
        farm, owner, cycle = budget_setup
        budget1 = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("200"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        budget2 = Budget.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.LABOUR,
            amount=Decimal("300"),
            period_start=date.today() - timedelta(days=30),
            period_end=date.today() + timedelta(days=30),
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.INPUTS,
            amount=Decimal("300"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )
        Expense.objects.create(
            farm=farm,
            cycle=cycle,
            category=ExpenseCategory.LABOUR,
            amount=Decimal("400"),
            date=date.today(),
            status=ExpenseStatus.POSTED,
        )

        check_budget_overruns()

        notifications = Notification.objects.filter(
            user=owner, type=NotificationType.ALERT
        )
        assert notifications.count() == 2
