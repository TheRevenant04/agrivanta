# Agrivanta — Implementation Backlog

**Stack:** Django 5 + DRF backend · PostgreSQL · Celery + Redis · React 18 + TypeScript (Vite) frontend
**Principle:** Each task is self-contained, session-sized, and independently hand-off-able. Tasks are ordered by dependency; later tasks assume earlier ones are done but do not require reading them — requirements are restated inline.

---

## Phase 0 — Project bootstrap

## 1. Empty project with passing test
Goal: Prove the toolchain works end to end with a minimal green test.
Description: Create the repository layout (`backend/`, `frontend/`, `docs/`) with a Django project skeleton, a Postgres-backed test database configuration, and one trivial health-check test that passes under `pytest`. Include a README with setup instructions and a `.gitignore`.

## 2. Frontend scaffold with passing test
Goal: Prove the frontend toolchain works end to end.
Description: Scaffold a Vite + React + TypeScript app in `frontend/` with ESLint, Prettier, and Vitest configured. Add one trivial component test that passes and wire an npm script to run it.

## 3. CI pipeline
Goal: Run backend and frontend tests automatically on every push.
Description: Create a GitHub Actions workflow that installs Python and Node dependencies, spins up Postgres as a service container, runs `pytest` for the backend and `vitest` for the frontend, and fails the build on any test failure.

## 4. Docker Compose for local development
Goal: One command brings up the full local stack.
Description: Write a `docker-compose.yml` that runs Postgres, Redis, the Django development server, and Celery worker with health checks. Document the commands in the README.

---

## Phase 1 — Core platform: auth, users, farm config

## 5. Custom user model with roles
Goal: Users exist and carry a farm-level role.
Description: Replace Django's default user model with a custom one supporting email login and a role field with values `owner`, `manager`, `worker`. Write tests for user creation and role assignment.

## 6. Authentication endpoints
Goal: Users can register, log in, and log out via the API.
Description: Implement DRF endpoints for registration, login (token or session), logout, and current-user retrieval using `dj-rest-auth` or equivalent. Write API tests covering success and failure cases.

## 7. Role-based permission framework
Goal: API access is enforceable by role.
Description: Implement DRF permission classes for the three roles and a decorator/mixin to apply them to views. Write tests that verify each role is allowed or denied on a dummy protected endpoint.

## 8. Farm and field models and CRUD
Goal: One farm and its fields can be configured.
Description: Create `Farm` (one per business, with name and reporting currency) and `Field` (belongs to farm, name, area, optional polygon/notes) models with full DRF CRUD endpoints and tests. Enforce that a user belongs to exactly one farm.

## 9. Crops, varieties, and units of measure
Goal: User-defined crops, varieties, and measurement units exist.
Description: Create models for `Crop`, `Variety` (belongs to crop), and `Unit` (with a base-measure category, e.g. mass/volume/count) scoped to the farm. Add CRUD endpoints and tests.

## 10. Unit conversion rules
Goal: Units can be converted deterministically.
Description: Add a `UnitConversion` model (from-unit, to-unit, factor) and a pure calculation function that converts quantities between compatible units, raising a clear error when no rule exists. Write unit tests covering conversions, inverse conversions, and missing-rule cases.

## 11. Crop cycles
Goal: Independent, possibly overlapping crop cycles can be tracked per field.
Description: Create a `CropCycle` model (field, crop, variety, start date, optional end date, status: open/closed, expected yield and price fields) with CRUD endpoints. Support multiple concurrent cycles on one field and annual vs. perennial designation. Write tests including an overlapping-cycles scenario.

## 12. Agricultural seasons and reporting periods
Goal: Reporting can be sliced by calendar periods and farm-defined seasons.
Description: Create `Season` (name, start/end date, optional year) and `ReportingPeriod` models scoped to the farm, with CRUD endpoints and tests. Seasons may overlap calendar years.

---

## Phase 2 — Operations, inventory, resources

## 13. Activity types and templates
Goal: Standard and custom activity types can be defined.
Description: Create an `ActivityType` model (name, category such as land preparation/planting/fertilizing/spraying/harvesting, default resource fields) seeded with the standard templates on farm creation. Add CRUD endpoints and tests.

## 14. Activities with statuses
Goal: Planned farm activities are tracked through to completion.
Description: Create an `Activity` model (crop cycle, activity type, planned date, status: planned/in_progress/completed/overdue, description) with CRUD endpoints. Write tests for status transitions. Overdue detection is a separate task.

## 15. Activity resource needs
Goal: Activities can plan input quantities, labour, and equipment.
Description: Add models linking activities to planned input items (inventory item + quantity), planned labour hours, and planned equipment. Include CRUD via nested endpoints and tests.

## 16. Inventory items and stock movements
Goal: Input stock purchases and usage are tracked with running quantities.
Description: Create `InventoryItem` (name, unit, reorder level) and `StockMovement` (item, type: purchase/usage/adjustment, quantity, unit cost, date, linked activity/expense) models. Derive current quantity from movements; write tests for purchase-then-usage scenarios and low-stock threshold detection.

## 17. Worker profiles and labour records
Goal: Workers are profiled and their assigned hours and costs are recorded.
Description: Create a `Worker` profile model (linked to user or standalone) and a `LabourRecord` model (worker, activity, hours, hourly cost, date). Add CRUD endpoints and tests computing total labour cost per activity.

## 18. Equipment and usage records
Goal: Equipment usage and associated operating costs are recorded.
Description: Create an `Equipment` model (name, farm-scoped) and `EquipmentUsage` model (equipment, activity, hours, cost per hour or total cost, date). Add CRUD endpoints and tests.

## 19. Suppliers and customers
Goal: Basic counterparty profiles exist and link to transactions.
Description: Create `Supplier` and `Customer` models (name, contact fields, notes) with CRUD endpoints and tests. Foreign keys from purchases and sales will be added in later tasks.

---

## Phase 3 — Finance: expenses, payments, budgets

## 20. Expense categories and expense records
Goal: Purchases, expenses, and overheads are recorded against categories.
Description: Create `ExpenseCategory` (seeded defaults: inputs, labour, equipment, overhead, other) and `Expense` models (category, amount, date, supplier optional, attachments optional, status: draft/posted). Add CRUD endpoints and tests distinguishing draft from posted.

## 21. Posted-transaction immutability
Goal: Posted transactions cannot be edited or deleted; corrections use reversal.
Description: Implement service-layer and database-level enforcement that `posted` expenses (and later all financial records) reject update and delete. Create a `Reversal` mechanism that creates a compensating record and marks the original reversed. Write tests proving edits are blocked and reversal preserves history.

## 22. Full audit history
Goal: Every change to sensitive records is traceable.
Description: Integrate `django-auditlog` (or a custom change-log model) to record actor, timestamp, and before/after values on farm, crop cycle, expense, and inventory models. Write a test that performs a change and asserts an audit entry exists.

## 23. Payments and money received/paid
Goal: Basic money-in and money-out is recorded and linked.
Description: Create a `Payment` model (type: received/paid, amount, date, linked expense or sale, optional reference) with CRUD endpoints. Tests verify linking and that unlinked standalone payments work.

## 24. Attachment uploads
Goal: Receipts and supplier invoices can be uploaded and linked to transactions.
Description: Implement file upload storage (local disk for dev, S3-compatible interface) and an `Attachment` model linkable to expenses and payments. Add upload/list/delete endpoints and tests including size/type validation.

## 25. Cost allocation rules
Goal: Shared overheads can be allocated to fields or crop cycles reproducibly.
Description: Create an `AllocationRule` model (name, basis: e.g. per-hectare/per-cycle-share, parameters, active period) and a pure calculation function that allocates a shared cost across targets using a rule. Write unit tests for each basis including edge cases (single target, zero area).

## 26. Crop-cycle budgets
Goal: Overall and category-level budgets exist per crop cycle.
Description: Create a `Budget` model (crop cycle or farm scope, category optional, amount, period) with CRUD endpoints and tests. Budget-versus-actual reporting is a later task.

## 27. Recurring expense templates and reminders
Goal: Recurring expenses generate reminders but never auto-create transactions.
Description: Create a `RecurringExpenseTemplate` model (category, amount, frequency, next due date) and a Celery beat task that raises an in-app reminder when a template is due. Tests verify a reminder is created and that no transaction is auto-generated.

---

## Phase 4 — Harvests, sales, and calculations

## 28. Harvest records
Goal: Harvest quantity, date, field, crop cycle, and unit are recorded.
Description: Create a `Harvest` model with CRUD endpoints linked to a crop cycle. Tests verify quantities aggregate per crop cycle and respect unit conversions from task 10.

## 29. Sales and revenue records
Goal: Sales are recorded with customer, crop, quantity, price, and date.
Description: Create a `Sale` model (customer, crop cycle or harvest link, quantity, unit price, date) linked to the `Customer` model from task 19. Write tests verifying revenue computation and that sold quantity cannot exceed harvested quantity minus already-sold (soft validation with clear error).

## 30. Harvested vs. sold vs. unsold reporting query
Goal: Harvested, sold, unsold produce, and actual revenue are distinguishable.
Description: Implement a service function returning, per crop cycle, harvested quantity, sold quantity, unsold balance, and revenue. Write unit tests with multiple harvests and sales including partial sales.

## 31. Deterministic profitability calculation module
Goal: Crop-cycle profitability is computed by pure, tested functions.
Description: Write pure Python functions (no Django dependencies) that compute crop-cycle operating surplus (revenue − direct costs) and result after allocated overheads, given plain input data structures. Write unit tests with known expected outputs covering missing-data errors (raise, never silently zero).

## 32. Break-even calculation module
Goal: Break-even quantity/price is computed from recorded costs and explicit assumptions.
Description: Write pure functions computing break-even yield and break-even price given fixed costs, variable costs, and assumption inputs. Tests verify formulas against hand-calculated scenarios and that missing assumptions raise explicit errors.

## 33. Farming-period KPI aggregation service
Goal: Profitability can be aggregated by field, crop cycle, season, and farm.
Description: Implement DRF endpoints that call the pure calculation module (tasks 31–32) with data assembled per grouping. Write API tests comparing aggregations against known fixture data.

---

## Phase 5 — Imports, notifications, reporting UX

## 34. CSV/Excel upload with validation and preview
Goal: Uploaded import files are parsed and validated before any write.
Description: Implement an import service accepting CSV and Excel for expenses and inventory movements: parse, validate rows, detect duplicates, and return a preview payload with per-row errors. Write tests with valid, invalid, and mixed files.

## 35. Import confirmation and commit
Goal: Imports are only written after explicit user confirmation.
Description: Build the commit step that takes a validated preview (tokenized server-side) and persists only confirmed rows, recording an audit entry. Write tests proving nothing is written before confirmation and partial correction-then-import works.

## 36. In-app notification model and API
Goal: Users receive in-app notifications.
Description: Create a `Notification` model (user, type, message, read flag) with list/mark-read endpoints. Write tests for creation and read-state transitions.

## 37. Scheduled notification jobs
Goal: Overdue activities, low stock, and budget overruns raise notifications.
Description: Implement Celery tasks that scan for overdue activities (task 14), inventory below reorder level (task 16), and budgets exceeded (task 26), creating notifications once per condition. Write tests invoking the tasks directly against fixture data.

## 38. Guided farm setup flow
Goal: A new user is walked through configuring farm, fields, crops, and an initial cycle.
Description: Build a frontend multi-step onboarding wizard that calls existing setup APIs (tasks 8–11) and tracks completion state. Include a backend "setup status" endpoint. Write component tests for step progression and an integration test for the full flow.

---

## Phase 6 — Reporting and exports

## 39. Operational report endpoints
Goal: Predefined operational reports are available via API.
Description: Implement read-only endpoints for activity status summaries, inventory position, labour and equipment usage, per the plan's report list. Write API tests against fixture data.

## 40. Budget-versus-actual report
Goal: Budgets are compared to actuals with transparent variance.
Description: Implement an endpoint returning per-budget actual spend, variance, and percentage, using the allocation and calculation services. Tests cover over/under budget and multi-category cycles.

## 41. Report export as CSV and Excel
Goal: Generated reports export to CSV and Excel.
Description: Implement an export service and endpoints that render any report payload to CSV and `.xlsx` using a shared serializer layer. Write tests validating file structure and cell values.

## 42. Report export as PDF
Goal: Generated reports export to PDF.
Description: Implement PDF rendering (WeasyPrint or headless-Chromium service) for the report set with a consistent layout including farm name, reporting period, and generation timestamp. Write tests asserting the file is a valid PDF with expected page content.

## 43. KPI dashboard endpoint
Goal: A single dashboard payload powers the main KPI view.
Description: Implement an endpoint returning headline KPIs (current-cycle spend, revenue to date, unsold produce, upcoming/overdue activities, low-stock count) for the farm with an optional period filter. Write tests against fixture data.

---

## Phase 7 — Frontend application

## 44. Frontend API client and auth flow
Goal: The React app can authenticate and call the API with typed contracts.
Description: Generate a typed API client from the OpenAPI schema, implement login/logout/register pages, token storage, and route guards for authenticated areas. Write component/integration tests for the auth flow.

## 45. Farm setup screens
Goal: Farm, fields, crops, varieties, and units are configurable in the UI.
Description: Build list/create/edit screens for farm configuration entities (tasks 8–10) with form validation mirroring backend rules. Write component tests for validation errors and successful submission.

## 46. Crop cycle screens
Goal: Crop cycles can be created, viewed, and closed in the UI.
Description: Build screens listing crop cycles per field with status badges, create/edit forms, and a close-cycle action with confirmation. Write component tests including the close-confirmation path.

## 47. Activity planning screens
Goal: Production plans and activities are manageable in the UI.
Description: Build screens for activity templates, activity CRUD, resource-needs editing, and status updates, filtered by crop cycle. Write component tests for status transitions.

## 48. Inventory screens
Goal: Stock items and movements are manageable in the UI.
Description: Build inventory item CRUD and stock movement entry screens showing current quantities and low-stock highlighting. Write component tests including low-stock badge rendering.

## 49. Expense and payment entry screens
Goal: Expenses, purchases, and payments are enterable via forms.
Description: Build forms for expenses (with category, supplier, attachment upload) and payments, distinguishing draft vs. posted states in the UI and hiding edit/delete for posted records. Write component tests for the posted-state restrictions.

## 50. Harvest and sale entry screens
Goal: Harvests and sales are enterable via forms.
Description: Build harvest and sale entry forms linked to crop cycles, surfacing the sold-exceeds-harvested validation error clearly. Write component tests including the error display case.

## 51. Import wizard UI
Goal: Users can upload, preview, correct, and confirm imports.
Description: Build a multi-step import wizard: file upload, preview table with row errors highlighted, inline correction for invalid rows, duplicate review, and a confirm button. Write component tests for the error-highlighting and confirm-disabled states.

## 52. Dashboard and report screens
Goal: KPIs and reports are visible and exportable.
Description: Build the KPI dashboard (charts for trends and comparisons) and report screens with period/season filters and CSV/Excel/PDF export buttons. Write component tests for filter changes triggering refetch.

## 53. Notifications UI
Goal: Users see and dismiss in-app notifications.
Description: Build a notification bell with unread count, a notifications list panel, and mark-as-read interaction using the API from task 36. Write component tests for unread-badge updates.

---

## Phase 8 — AI analyst

## 54. Provider-neutral LLM interface
Goal: LLM calls are isolated behind a swappable interface.
Description: Implement a thin abstraction (protocol/adapter) over one hosted LLM provider with streaming support and a fake implementation for tests. Write unit tests using the fake adapter. No farm logic yet.

## 55. Read-only farm query tools
Goal: A curated set of permission-scoped, deterministic query tools exists for the AI.
Description: Implement tool functions (e.g., get crop-cycle costs, get profitability by field, get inventory position, list activities) that query the database, enforce the requesting user's role permissions, and return structured results. Write tests for each tool including permission-denied and missing-data cases.

## 56. AI chat orchestration
Goal: A chat endpoint answers questions using tools with traceable evidence.
Description: Implement a DRF chat endpoint: send the user question plus permitted tool definitions to the LLM, execute tool calls, feed results back, and return the final answer wrapped in an evidence object (figures used, periods, crop cycles, calculation basis). Write tests with the fake adapter covering a multi-tool question and a data-insufficient question.

## 57. Insufficient-data and error handling in AI answers
Goal: The AI explains limitations instead of guessing.
Description: Configure the orchestration so missing/invalid data produces an explicit explanation identifying what is missing, never fabricated numbers or silent zeros. Write tests asserting refusal/limitation responses for empty datasets and invalid parameters.

## 58. AI chat UI
Goal: Users can ask questions and see evidence-backed answers in the app.
Description: Build a chat interface showing the conversation, streaming responses, and a collapsible evidence panel per answer. Write component tests for rendering answers with evidence and error states.

---

## Phase 9 — Hardening, AI evals, deployment

## 59. AI golden-question eval suite
Goal: AI answer accuracy and calculation correctness are regression-tested.
Description: Create a seeded fixture farm dataset and a golden set of questions with expected figures/answers. Implement a pytest harness that runs the full orchestration against the fake and real (optionally) adapters, asserting calculation values and evidence presence. Wire into CI as a separate job.

## 60. Health checks, structured logging, and error tracking
Goal: The app is observable in production.
Description: Add `/healthz` and `/readyz` endpoints, configure structlog with request correlation IDs, and integrate Sentry for backend and frontend. Write tests asserting health endpoint behavior when the database is unavailable.

## 61. Database backup and restore procedure
Goal: Backups run automatically and restore is documented and tested.
Description: Configure automated daily Postgres backups (provider or pg_dump job), write a documented restore runbook, and perform a test restore into a scratch environment verifying row counts. Store the runbook in `docs/`.

## 62. Production deployment pipeline
Goal: Main branch deploys automatically with zero-downtime migrations.
Description: Set up a deployment workflow (Docker images + chosen host) that runs migrations safely, deploys backend, Celery, and frontend, and smoke-tests the health endpoint post-deploy. Document the environment variables and rollback steps.

## 63. End-to-end success-workflow test
Goal: The MVP success path is verified automatically.
Description: Write a Playwright suite covering the plan's end-to-end workflow: configure farm → plan activities → record inventory/expenses/labour → track budgets → record harvests/sales → close cycle → generate a report → ask the AI a question and receive an evidence-backed answer. Run it in CI against the full local stack.
