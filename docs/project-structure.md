# Project Structure

Complete directory layout and module organization for Agrivanta.

---

## Repository Root

```
agrivanta/
├── backend/                    # Django REST API
├── frontend/                   # React + TypeScript SPA
├── docs/                       # Documentation
├── custom-agent/               # Headless PM/Engineer/QA orchestrator
├── mcp-server/                 # Read-only backlog + issues MCP server
├── .agents/                    # Portable agent definitions
├── .opencode/                  # OpenCode configuration
├── docker-compose.yml          # Development stack
├── docker-compose.prod.yml     # Production-like stack
├── .env.dev.example            # Dev environment template
├── .env.prod.example           # Prod environment template
├── AGENTS.md                   # Agent workflow rules
└── README.md
```

---

## Backend (`backend/`)

```
backend/
├── api/                        # Main API application
│   ├── __init__.py
│   ├── apps.py                 # AppConfig
│   ├── models/                 # Domain models (split by domain)
│   │   ├── __init__.py
│   │   ├── farm.py             # Farm, Field
│   │   ├── crop.py             # Crop, Variety, Unit, Conversion
│   │   ├── crop_cycle.py       # CropCycle, Season, ReportingPeriod
│   │   ├── activity.py         # Activity, ActivityType
│   │   ├── inventory.py        # InventoryItem, StockMovement
│   │   ├── financial.py        # Expense, Payment, Budget, Supplier, Customer
│   │   ├── production.py       # Harvest, Sale
│   │   ├── notification.py     # Notification
│   │   ├── attachment.py       # Attachment
│   │   ├── chat.py             # ChatConversation, ChatMessage, ChatEvaluation
│   │   └── audit.py            # AuditLog, ImportBatch
│   ├── views/                  # ViewSets (DRF)
│   │   ├── __init__.py
│   │   ├── farm.py
│   │   ├── crop.py
│   │   ├── crop_cycle.py
│   │   ├── activity.py
│   │   ├── inventory.py
│   │   ├── financial.py
│   │   ├── production.py
│   │   ├── reports.py
│   │   ├── chat.py
│   │   └── imports.py
│   ├── serializers/            # DRF serializers
│   │   ├── __init__.py
│   │   ├── farm.py
│   │   ├── crop.py
│   │   ├── crop_cycle.py
│   │   ├── activity.py
│   │   ├── inventory.py
│   │   ├── financial.py
│   │   ├── production.py
│   │   ├── reports.py
│   │   ├── chat.py
│   │   └── imports.py
│   ├── permissions/            # Custom permission classes
│   │   ├── __init__.py
│   │   └── farm_scope.py       # Farm-scoped access control
│   ├── filters/                # Django-filter FilterSets
│   │   ├── __init__.py
│   │   └── ...
│   ├── pagination/             # Custom pagination
│   │   ├── __init__.py
│   │   └── standard.py
│   ├── exports/                # Report exports (PDF/Excel/CSV)
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── pdf.py
│   │   ├── excel.py
│   │   └── csv.py
│   ├── ai/                     # AI chat integration
│   │   ├── __init__.py
│   │   ├── tools/              # Function-calling tools
│   │   │   ├── __init__.py
│   │   │   ├── profitability.py
│   │   │   ├── inventory.py
│   │   │   ├── activities.py
│   │   │   └── registry.py
│   │   ├── prompts/
│   │   │   └── system.md
│   │   ├── client.py           # LLM client wrapper
│   │   └── handler.py          # Chat endpoint logic
│   ├── management/             # Custom management commands
│   │   └── commands/
│   │       ├── ingest_sample_data.py
│   │       └── backup_database.py
│   ├── services/               # Business logic layer
│   │   ├── __init__.py
│   │   ├── profitability.py
│   │   ├── inventory.py
│   │   ├── budgets.py
│   │   └── break_even.py
│   ├── utils/                  # Shared utilities
│   │   ├── __init__.py
│   │   ├── calculations.py
│   │   ├── dates.py
│   │   └── units.py
│   ├── tests/                  # Test suites
│   │   ├── __init__.py
│   │   ├── conftest.py         # Pytest fixtures
│   │   ├── factories.py        # Factory Boy factories
│   │   ├── unit/               # Fast, isolated tests
│   │   │   ├── test_models.py
│   │   │   ├── test_serializers.py
│   │   │   ├── test_services/
│   │   │   └── test_ai_tools.py
│   │   └── integration/        # DB, API, full-stack tests
│   │       ├── test_views.py
│   │       ├── test_permissions.py
│   │       ├── test_filters.py
│   │       ├── test_reports.py
│   │       ├── test_chat.py
│   │       └── test_imports.py
│   └── urls.py                 # API URL routing
├── config/                     # Django project configuration
│   ├── __init__.py
│   ├── asgi.py
│   ├── wsgi.py
│   ├── urls.py                 # Root URL config
│   └── settings/
│       ├── __init__.py
│       ├── base.py             # Shared settings
│       ├── development.py      # Dev overrides (DEBUG=True, etc.)
│       └── production.py       # Prod hardening
├── media/                      # User uploads (gitignored)
├── static/                     # Collected static files (gitignored)
├── locale/                     # Translations (future)
├── manage.py                   # Django CLI
├── pyproject.toml              # Project metadata, dependencies
├── uv.lock                     # Locked dependencies
├── Dockerfile                  # Multi-stage build
├── .dockerignore
├── .python-version             # Python version pin (3.13)
└── README.md
```

---

## Frontend (`frontend/`)

```
frontend/
├── src/
│   ├── app/                    # App shell, routing, providers
│   │   ├── AppRoutes.tsx       # Route definitions
│   │   ├── AppShell.tsx        # Layout with sidebar/header
│   │   ├── Providers.tsx       # Context providers (query, services, auth)
│   │   └── ProtectedRoute.tsx  # Auth guard
│   ├── components/             # Reusable UI components
│   │   ├── ui/                 # shadcn/ui primitives (button, input, table, etc.)
│   │   ├── layout/             # Sidebar, Header, Breadcrumbs
│   │   ├── forms/              # FormField, FormSelect, FormDatePicker
│   │   ├── tables/             # DataTable, ColumnDef
│   │   ├── charts/             # KPIChart, TrendChart, ComparisonChart
│   │   ├── chat/               # ChatWindow, MessageBubble, Citations
│   │   ├── imports/            # ImportWizard, PreviewTable
│   │   ├── reports/            # ReportToolbar, ExportDropdown
│   │   └── common/             # Loading, EmptyState, ErrorBoundary
│   ├── pages/                  # Route-level page components
│   │   ├── dashboard/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── KPICards.tsx
│   │   │   └── TrendCharts.tsx
│   │   ├── farm/
│   │   │   ├── FarmSettingsPage.tsx
│   │   │   ├── FieldsPage.tsx
│   │   │   └── FieldForm.tsx
│   │   ├── crops/
│   │   │   ├── CropsPage.tsx
│   │   │   ├── VarietiesPage.tsx
│   │   │   └── UnitsPage.tsx
│   │   ├── crop-cycles/
│   │   │   ├── CropCyclesPage.tsx
│   │   │   ├── CropCycleDetailPage.tsx
│   │   │   └── CloseCropCycleDialog.tsx
│   │   ├── activities/
│   │   │   ├── ActivitiesPage.tsx
│   │   │   ├── ActivityForm.tsx
│   │   │   └── ActivityTemplatesPage.tsx
│   │   ├── inventory/
│   │   │   ├── InventoryPage.tsx
│   │   │   ├── StockMovementsPage.tsx
│   │   │   └── LowStockAlerts.tsx
│   │   ├── financials/
│   │   │   ├── ExpensesPage.tsx
│   │   │   ├── PaymentsPage.tsx
│   │   │   ├── BudgetsPage.tsx
│   │   │   └── SuppliersCustomersPage.tsx
│   │   ├── production/
│   │   │   ├── HarvestsPage.tsx
│   │   │   └── SalesPage.tsx
│   │   ├── reports/
│   │   │   ├── ReportsPage.tsx
│   │   │   ├── ProfitabilityReport.tsx
│   │   │   ├── YieldComparison.tsx
│   │   │   └── BreakEvenReport.tsx
│   │   ├── chat/
│   │   │   └── ChatPage.tsx
│   │   ├── imports/
│   │   │   └── ImportPage.tsx
│   │   ├── auth/
│   │   │   ├── LoginPage.tsx
│   │   │   └── RegisterPage.tsx
│   │   └── settings/
│   │       └── SettingsPage.tsx
│   ├── services/               # Typed API client layer
│   │   ├── types.ts            # Service contract (AgrivantaServices)
│   │   ├── httpServices.ts     # Fetch wrapper with auth
│   │   ├── mockServices.ts     # In-memory implementation
│   │   ├── createServices.ts   # Factory selecting mock/http
│   │   ├── servicesContext.tsx # React context provider
│   │   └── generated/          # OpenAPI-generated (committed)
│   │       ├── schemas.ts
│   │       ├── operations.ts
│   │       └── index.ts
│   ├── hooks/                  # Custom React hooks
│   │   ├── useAuth.ts
│   │   ├── useServices.ts
│   │   ├── useDebounce.ts
│   │   ├── useLocalStorage.ts
│   │   └── useMediaQuery.ts
│   ├── stores/                 # Zustand client state
│   │   ├── authStore.ts
│   │   ├── uiStore.ts
│   │   └── reportStore.ts
│   ├── lib/                    # Utilities
│   │   ├── utils.ts            # cn(), formatters, validators
│   │   ├── date.ts             # Date formatting, periods
│   │   ├── number.ts           # Currency, unit formatting
│   │   └── export.ts           # Blob download helpers
│   ├── styles/                 # Global styles
│   │   ├── globals.css         # Tailwind imports, base styles
│   │   └── theme.css           # CSS variables, dark mode
│   ├── types/                  # Shared TypeScript types
│   │   ├── api.ts              # Generated API types (re-export)
│   │   ├── domain.ts           # Frontend domain models
│   │   └── ui.ts               # UI-specific types
│   ├── constants/              # Application constants
│   │   ├── routes.ts
│   │   ├── roles.ts
│   │   └── activityTypes.ts
│   ├── main.tsx                # App entry point
│   └── vite-env.d.ts           # Vite type declarations
├── public/                     # Static assets served as-is
│   ├── favicon.ico
│   ├── logo.svg
│   └── manifest.json
├── dist/                       # Production build output (gitignored)
├── node_modules/               # Dependencies (gitignored)
├── package.json
├── package-lock.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── components.json             # shadcn/ui configuration
├── .eslintrc.json
├── .prettierrc
├── .nvmrc                      # Node version (24.x)
├── .npmrc                      # engine-strict=true
├── .env.example
├── Dockerfile
├── .dockerignore
└── README.md
```

---

## Documentation (`docs/`)

```
docs/
├── getting-started.md          # Local setup, Docker, first login
├── architecture.md             # System design, data flows, infra
├── api-reference.md            # Complete REST API reference
├── deployment.md               # Production deployment guide
├── development.md              # Coding standards, workflow, testing
├── configuration.md            # Environment variables reference
├── project-structure.md        # This file
└── database-restore.md         # Backup/restore procedures
```

---

## Supporting Tools

### Custom Agent (`custom-agent/`)

```
custom-agent/
├── agent.py                    # Headless orchestrator entry point
├── pm.py                       # Product Manager subagent
├── engineer.py                 # Software Engineer subagent
├── qa.py                       # QA Engineer subagent
├── reviewer.py                 # Code Reviewer subagent
├── state.py                    # Issue lifecycle state machine
├── github.py                   # GitHub API wrapper
└── requirements.txt
```

### MCP Server (`mcp-server/`)

```
mcp-server/
├── server.py                   # FastMCP server entry point
├── backlog.py                  # Task.md parsing
├── issues.py                   # GitHub issues listing
└── requirements.txt
```

### Agent Definitions (`.agents/`)

```
.agents/
├── skills/                     # Portable skills
│   ├── groom-issue/
│   ├── implement-issue/
│   └── review-pr/
├── subagents/                  # Subagent definitions
│   ├── pm.md
│   ├── engineer.md
│   ├── qa.md
│   └── reviewer.md
└── index.json                  # Registry
```

### OpenCode Config (`.opencode/`)

```
.opencode/
├── opencode.json               # Main config
├── plugins/
│   └── guardrails.js           # Command allow/deny
└── agents/                     # OpenCode-specific agents
```

---

## Key Architectural Patterns

### Backend: Domain-Driven Structure
- Models grouped by business domain (`models/farm.py`, `models/inventory.py`, etc.)
- Views, serializers, filters mirror model organization
- Services layer (`api/services/`) contains pure business logic
- AI tools in `api/ai/tools/` are stateless, deterministic functions

### Frontend: Feature-Based with Shared Primitives
- `components/ui/` = shadcn primitives (never modify directly)
- `components/<feature>/` = composed feature components
- `pages/<feature>/` = route-level composition
- `services/` = single API contract, dual implementation (mock/http)

### Shared: Generated Code
- `frontend/src/services/generated/` = OpenAPI → TypeScript (committed)
- Backend `openapi.yaml` = source of truth for API contract

---

## File Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| Python modules | `snake_case.py` | `crop_cycle.py` |
| Python classes | `PascalCase` | `CropCycle` |
| Python functions | `snake_case` | `calculate_profitability` |
| TypeScript files | `PascalCase.tsx` / `camelCase.ts` | `CropCycleForm.tsx`, `useAuth.ts` |
| React components | `PascalCase.tsx` | `DashboardPage.tsx` |
| Hooks | `use<Name>.ts` | `useServices.ts` |
| Stores | `<name>Store.ts` | `authStore.ts` |
| Types | `PascalCase` | `CropCycleData` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE` |
| CSS classes | Tailwind utilities | `flex items-center gap-2` |
| Database tables | `api_<model>` | `api_cropcycle` |
| Environment vars | `UPPER_SNAKE_CASE` | `DJANGO_SECRET_KEY` |

---

## Git Ignore Patterns

Key `.gitignore` entries (per folder):

```
# Backend
backend/media/
backend/static/
backend/db.sqlite3
backend/__pycache__/
backend/.pytest_cache/
backend/.mypy_cache/
backend/.ruff_cache/
backend/*.log

# Frontend
frontend/node_modules/
frontend/dist/
frontend/.vite/
frontend/*.log

# Root
.env
.env.*
*.pyc
__pycache__/
.DS_Store
```

---

## Module Dependency Rules

### Backend
```
config/settings → api/models → api/services → api/views → api/urls
                    ↓
              ai/tools (independent, used by chat handler)
```

### Frontend
```
app/Providers → services/createServices → services/httpServices|mockServices
                    ↓
         pages/* → components/* → hooks/* → lib/*
```

### Cross-Cutting
- `api/serializers` ↔ `frontend/src/services/generated` (via OpenAPI)
- `api/ai/prompts/system.md` → `api/ai/handler.py` → `api/views/chat.py` → frontend chat