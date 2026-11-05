# Issue #37 Implementation Summary: Scheduled Notification Jobs

## Completed Implementation

All acceptance criteria have been met. Three production-ready Celery tasks have been implemented with comprehensive test coverage.

## Files Created

### 1. `backend/config/celery.py`
- Celery app initialization
- Auto-discovery of tasks from the api app
- Debug task for testing

### 2. `backend/config/__init__.py` (updated)
- Imports celery_app to ensure it's loaded when Django starts

### 3. `backend/config/settings.py` (updated)
- Added Celery configuration:
  - CELERY_BROKER_URL (Redis, default: localhost:6379/0)
  - CELERY_RESULT_BACKEND (Redis)
  - CELERY_ACCEPT_CONTENT = ["json"]
  - CELERY_TASK_SERIALIZER = "json"
  - CELERY_RESULT_SERIALIZER = "json"
  - CELERY_TIMEZONE = "UTC"

### 4. `backend/api/tasks.py` (new)
Contains three main Celery tasks:

#### check_overdue_activities()
- Detects activities with status PLANNED or IN_PROGRESS with planned_date < today
- Creates ALERT notifications for farm owners
- Deduplication: checks if notification already exists for the activity type
- Idempotent: rerunning doesn't create duplicates

#### check_low_stock()
- Iterates through all farms and inventory items
- Compares current_quantity (calculated from stock movements) against reorder_level
- Creates WARNING notifications for items below threshold
- Accounts for PURCHASE (+), USAGE (-), and ADJUSTMENT movements
- Deduplication: checks if notification already exists for the item name

#### check_budget_overruns()
- Compares budget.amount against actual spend (posted expenses only)
- Respects scope: cycle (if set) + category (if set) + period (if set)
- Creates ALERT notifications when spend exceeds budget
- Deduplication: checks if notification already exists for the budget category

### 5. `backend/api/tests/test_scheduled_notifications.py` (new)
Comprehensive test suite with 19 tests covering:

**TestOverdueActivities (6 tests)**
- Creates notification for overdue PLANNED activities
- Creates notification for overdue IN_PROGRESS activities
- No notification for future activities
- No notification for COMPLETED activities
- Idempotent: no duplicates on rerun
- Multiple activities handled correctly

**TestLowStockNotifications (5 tests)**
- Creates notification when stock < reorder_level
- No notification when stock >= reorder_level
- Accounts for usage movements (decrements)
- Idempotent: no duplicates on rerun
- Multiple items handled correctly

**TestBudgetOverruns (8 tests)**
- Creates notification when spend > budget
- No notification when spend <= budget
- Only counts POSTED expenses
- Respects budget cycle scope
- Respects budget category scope
- Respects budget period scope
- Idempotent: no duplicates on rerun
- Multiple overruns handled correctly

## Dependencies Added

- `celery>=5.4.0` - Distributed task queue
- `redis>=5.1.0` - Message broker and result backend

Added to `pyproject.toml` and synced via `uv sync`.

## Usage

### Invoke tasks directly (for testing/manual runs):
```python
from api.tasks import check_overdue_activities, check_low_stock, check_budget_overruns

check_overdue_activities()
check_low_stock()
check_budget_overruns()
```

### Or with Celery worker:
```bash
celery -A config worker -l info
```

### With Celery beat (for scheduling, future implementation):
```python
# In settings.py
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'check-overdue-activities': {
        'task': 'api.tasks.check_overdue_activities',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
    },
    'check-low-stock': {
        'task': 'api.tasks.check_low_stock',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    'check-budget-overruns': {
        'task': 'api.tasks.check_budget_overruns',
        'schedule': crontab(minute=0, hour='*/12'),
    },
}
```

## Test Results

All 418 tests passing (including 19 new tests):
```
418 passed in 144.57s
```

## Key Design Decisions

1. **Deduplication Strategy**: Instead of tracking notifications in a separate table, we check for existing notifications with matching message patterns. This keeps the implementation simple and allows easy updates of notification content.

2. **Farm Owner Notification**: Only the farm owner is notified. Future enhancements could notify managers as well.

3. **Scope Handling for Budgets**: Budgets can be scoped by:
   - Cycle: only expenses for that cycle count
   - Category: only expenses in that category count
   - Period: only expenses within that date range count
   - Combinations: all constraints apply with AND logic

4. **Stock Movement Calculation**: Uses the existing InventoryItem.current_quantity() method which:
   - Sums PURCHASE movements (positive)
   - Subtracts USAGE movements (negative)
   - Adds/subtracts ADJUSTMENT movements (based on quantity sign)

5. **Posted Expenses Only**: Budget calculations only include POSTED expenses, not DRAFT, to ensure only confirmed expenses affect budget status.

## Acceptance Criteria Met

✅ Celery tasks exist for: check overdue activities, low stock, budget overruns
✅ Overdue detection uses activity status logic from task 14
✅ Low stock checks inventory items vs reorder level using stock movements from task 16
✅ Budget overruns detected by comparing budget amount to actual spend
✅ Notifications created only once per condition per entity (deduplication)
✅ Notifications created with correct user, type, and message
✅ Tasks can be invoked directly in tests
✅ Celery/Redis configured
✅ pytest tests pass
✅ Idempotent: rerunning doesn't duplicate notifications

## Future Enhancements

1. Add Celery Beat schedule configuration for automated periodic runs
2. Extend notification recipients to include managers
3. Add notification preferences/suppression mechanism
4. Add email notifications in addition to in-app notifications
5. Add task retry logic with exponential backoff
6. Add monitoring/alerting for failed tasks
