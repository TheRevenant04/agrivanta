from django.urls import path

from . import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/me", views.MeView.as_view()),
    path("farm", views.FarmView.as_view()),
    path("seasons", views.SeasonListView.as_view()),
    path("seasons/<str:season_id>", views.SeasonDetailView.as_view()),
    path("reporting-periods", views.ReportingPeriodListView.as_view()),
    path(
        "reporting-periods/<str:period_id>",
        views.ReportingPeriodDetailView.as_view(),
    ),
    path("fields", views.FieldListView.as_view()),
    path("fields/<str:field_id>", views.FieldDetailView.as_view()),
    path("crops", views.CropListView.as_view()),
    path("crops/<str:crop_id>", views.CropDetailView.as_view()),
    path("varieties", views.VarietyListView.as_view()),
    path("varieties/<str:variety_id>", views.VarietyDetailView.as_view()),
    path("units", views.UnitListView.as_view()),
    path("units/<str:unit_id>", views.UnitDetailView.as_view()),
    path("conversions", views.ConversionListView.as_view()),
    path("conversions/convert", views.ConversionConvertView.as_view()),
    path("crop-cycles", views.CropCycleListView.as_view()),
    path(
        "crop-cycles/<str:cycle_id>",
        views.CropCycleDetailView.as_view(),
    ),
    path(
        "crop-cycles/<str:cycle_id>/close",
        views.CropCycleCloseView.as_view(),
    ),
    path("activity-types", views.ActivityTypeListView.as_view()),
    path("activities/cycles", views.ActivityCycleListView.as_view()),
    path("activities", views.ActivityListView.as_view()),
    path(
        "activities/<str:activity_id>",
        views.ActivityDetailView.as_view(),
    ),
    path(
        "activities/<str:activity_id>/status",
        views.ActivityStatusView.as_view(),
    ),
    path(
        "activities/<str:activity_id>/resource-needs",
        views.ActivityResourceNeedsView.as_view(),
    ),
    path("inventory-items", views.InventoryItemListView.as_view()),
    path(
        "inventory-items/<str:item_id>",
        views.InventoryItemDetailView.as_view(),
    ),
    path(
        "inventory-items/<str:item_id>/movements",
        views.ItemMovementListView.as_view(),
    ),
    path("stock-movements", views.StockMovementListView.as_view()),
    path("expenses", views.ExpenseListView.as_view()),
    path(
        "expenses/<str:expense_id>",
        views.ExpenseDetailView.as_view(),
    ),
    path(
        "expenses/<str:expense_id>/post",
        views.ExpensePostView.as_view(),
    ),
    path(
        "expenses/<str:expense_id>/attachments",
        views.ExpenseAttachmentView.as_view(),
    ),
    path("imports/preview", views.ImportPreviewView.as_view()),
    path("imports/commit", views.ImportCommitView.as_view()),
    path("notifications", views.NotificationListView.as_view()),
    path(
        "notifications/unread-count",
        views.NotificationUnreadCountView.as_view(),
    ),
    path(
        "notifications/read-all",
        views.NotificationMarkAllReadView.as_view(),
    ),
    path(
        "notifications/<str:notification_id>/read",
        views.NotificationMarkReadView.as_view(),
    ),
    path(
        "notifications/<str:notification_id>",
        views.NotificationDetailView.as_view(),
    ),
    path("payments", views.PaymentListView.as_view()),
    path("budgets", views.BudgetListView.as_view()),
    path("budgets/<str:budget_id>", views.BudgetDetailView.as_view()),
    path("harvests/cycles", views.HarvestCycleListView.as_view()),
    path(
        "harvests/cycles/<str:cycle_id>/summary",
        views.HarvestCycleSummaryView.as_view(),
    ),
    path("harvests", views.HarvestListView.as_view()),
    path("harvests/<str:harvest_id>", views.HarvestDetailView.as_view()),
    path("customers", views.CustomerListView.as_view()),
    path("sales", views.SaleListView.as_view()),
    path("sales/<str:sale_id>", views.SaleDetailView.as_view()),
    path(
        "reports/profitability",
        views.ProfitabilityReportView.as_view(),
    ),
    path("dashboard", views.DashboardView.as_view()),
]
