# Agrivanta

A **farm operations and profitability platform** for commercially managed crop farms. It unifies field-level production planning, inventory management, financial tracking, harvest and sales recording, and evidence-backed AI-powered analytics — giving farm owners and managers the visibility they need to run profitable operations.

---

## Table of Contents

- [Problem](#problem)
- [Demo](#demo)
- [Screenshots](#screenshots)
- [Features](#features)
- [How It Works](#how-it-works)
- [Data](#data)
- [Evaluation & Quality](#evaluation--quality)
- [Project Dependencies](#project-dependencies)
- [Getting Started](#getting-started)
- [Documentation](#documentation)
- [License](#license)

---

## Problem

Commercial crop farms operate on thin margins with complex, interconnected decisions: when to plant, how much fertilizer to apply, whether equipment costs are justified, which fields are truly profitable. Existing tools either focus narrowly on accounting (disconnected from field reality) or offer generic farm management without financial rigor.

**Agrivanta bridges this gap by design:**

| Challenge | Agrivanta's Approach |
|-----------|---------------------|
| **Fragmented data** | Single source of truth: operations, inventory, and financials linked at the crop-cycle level |
| **Opaque profitability** | Deterministic calculations with full audit trails — every figure traceable to source transactions |
| **Reactive decision-making** | Real-time KPIs, budget-vs-actual alerts, and an AI analyst that answers questions with evidence |
| **Compliance & audit risk** | Posted transactions are immutable; corrections require reversal-and-replacement with full history |
| **Seasonal complexity** | Supports overlapping crop cycles, perennial crops, agricultural seasons, and custom reporting periods |

---

## Features

### Farm & Production Operations
- **Farm configuration** — Fields, crops, varieties, measurement units with conversion rules
- **Crop cycles** — Independent cycles per field, overlapping annual/perennial support, formal closure with lock/unlock
- **Activity planning** — Standard templates (planting, fertilizing, spraying, harvesting) + custom activities with resources, labor, equipment, budgets, expected yields
- **Status tracking** — Planned → In Progress → Completed → Overdue with essential notifications

### Inventory & Resource Management
- **Inventory tracking** — Purchases, usage, current stock, costs per item; link consumption to crop-cycle profitability
- **Labor & equipment** — Worker profiles with assignments, hours, costs; equipment assignments with operating costs
- **Supplier/customer profiles** — Linked to purchases, sales, and transactions
- **Low-stock alerts** — Configurable thresholds with in-app notifications

### Financials, Budgets & Payments
- **Cost recording** — Purchases, expenses, direct costs, overheads with categorization
- **Budget management** — Crop-cycle and category-level budgets with variance reporting
- **Overhead allocation** — Farm-level or distributed to fields/cycles via transparent, reproducible rules
- **Break-even analysis** — Based on recorded costs and explicit assumptions
- **Recurring expense templates** — With reminders (no auto-generation)
- **Payment tracking** — Money in/out linked to sales and expenses

### Harvests & Sales
- **Harvest records** — Quantity, date, field, crop cycle, unit
- **Sales records** — Customer, crop, quantity, price, date
- **Inventory reconciliation** — Harvested vs. sold vs. unsold with actual revenue tracking

### Reporting & Profitability
- **Dashboard KPIs** — Visual trends, comparisons, period/season selectors
- **Predefined reports** — Operations, inventory, financials, harvests, sales, budgets, profitability
- **Multi-dimensional profitability** — By field, crop cycle, season, whole farm
- **Yield comparisons** — Cross-field with unit normalization and period identification
- **Exports** — PDF, Excel, CSV for all reports

### AI Analyst (Read-Only, Evidence-Backed)
- **Natural-language queries** — Across all farm data domains
- **Deterministic calculations** — Function-calling tools for math; LLM explains, never invents figures
- **Traceable evidence** — Every answer cites figures, fields/cycles, periods, calculation basis
- **Explicit uncertainty** — Distinguishes actuals, estimates, assumptions; explains missing data
- **Read-only guarantee** — No data mutation, no action prescriptions
- **Evaluated accuracy** — Automated factual correctness, relevance, and calculation tests

### Data Integrity & Compliance
- **Preview-and-confirm imports** — CSV/Excel with validation, duplicate detection, corrections before commit
- **Attachment linking** — Receipts/invoices attached to transactions
- **Immutable posted transactions** — Corrections via reversal-and-replacement with full history
- **Role-based access** — Owner, Farm Manager, Worker
- **Scheduled backups** — Documented restore procedures with validation

---

## How It Works

```
┌─────────────────┐     HTTPS/REST      ┌─────────────────┐
│   Frontend      │ ◄──────────────────► │    Backend      │
│  (React 18 +    │     JSON/NDJSON      │  (Django 5.2 +  │
│   TypeScript)   │                      │   DRF)          │
└─────────────────┘                      └────────┬────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    │                              │                              │
              ┌─────▼─────┐                ┌───────▼───────┐              ┌───────▼───────┐
              │ PostgreSQL│                │    Redis      │              │   Celery      │
              │   17      │                │     7         │              │   Worker      │
              └───────────┘                └───────────────┘              └───────────────┘
```

### Request Flow (Standard API)
```
Browser → Frontend (React) → HTTP/JSON → Django (DRF) → PostgreSQL
                              ↑                          ↓
                        TanStack Query               Models/Managers
                              ↓                          ↓
                        Components ← Serializers ← QuerySets
```

### AI Chat Flow
```
User Question
      ↓
Frontend → Streaming NDJSON → Django /chat endpoint
      ↓                            ↓
Chat UI ←────────────── LLM + Function Tools
                      (deterministic calculations)
                      ↓
            Evidence-backed answer with citations
```

### Data Ingestion & Imports
```
CSV/Excel File
      ↓
Preview API → Validation → Duplicate Detection → User Corrections
      ↓                                              ↓
                           Confirm Import → Batch Insert
      ↓                                              ↓
                        Stock Movements / Expenses / Harvests / Sales
```

---

## Data

The system touches **six categories of data**:

| Data Category | Description | Storage |
|---------------|-------------|---------|
| **Farm configuration** | Fields, crops, varieties, units, conversions, seasons, reporting periods | PostgreSQL (`api_field`, `api_crop`, `api_variety`, `api_unit`, `api_conversion`, `api_season`, `api_reportingperiod`) |
| **Operational records** | Crop cycles, activities, activity templates, inventory items, stock movements | PostgreSQL (`api_cropcycle`, `api_activity`, `api_activitytype`, `api_inventoryitem`, `api_stockmovement`) |
| **Financial records** | Expenses, payments, budgets, suppliers, customers, attachments | PostgreSQL (`api_expense`, `api_payment`, `api_budget`, `api_supplier`, `api_customer`, `api_attachment`) |
| **Production outcomes** | Harvests, sales, money received/paid | PostgreSQL (`api_harvest`, `api_sale`) |
| **AI interactions** | Chat conversations, questions, answers, tool calls, citations, evaluation scores | PostgreSQL (`api_chatconversation`, `api_chatmessage`, `api_chatevaluation`) |
| **System data** | Users, notifications, permissions, audit logs, import batches | PostgreSQL (`auth_user`, `api_notification`, `api_importbatch`, `api_auditlog`) |

**Key integrity guarantees:**
- All financial metrics calculated deterministically from source records
- Posted transactions immutable; corrections require reversal + replacement
- Full audit trail on every change with user attribution
- Closed crop cycles locked unless authorized user reopens

---

## Evaluation & Quality

### Backend Test Coverage
```
uv run pytest --cov=api
```
- Unit tests: models, serializers, services, calculations
- Integration tests: API views, permissions, filters, exports
- AI tool tests: deterministic calculation verification

### Frontend Test Coverage
```
npm run test -- --coverage
```
- Component tests: forms, tables, charts, chat UI
- Service layer tests: mock and HTTP implementations
- Integration tests: routing, authentication, state management

### AI Answer Quality
- **Factual accuracy** — Automated evaluation against known results
- **Calculation correctness** — Regression tests for every AI tool
- **Citation completeness** — Every answer must reference source data
- **Human review** — Sampled answers rated for relevance and clarity

### Performance Benchmarks
| Operation | Target |
|-----------|--------|
| Dashboard KPI load | < 500ms |
| Report generation (PDF) | < 3s |
| AI chat first token | < 2s |
| Import preview (10k rows) | < 5s |
| API p95 latency | < 200ms |

---

## Project Dependencies

### Python Runtime (`backend/pyproject.toml`)

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | ≥ 3.13 | Runtime, managed with [uv](https://docs.astral.sh/uv/) |
| Django | 5.2 | Web framework |
| djangorestframework | 3.15 | REST API |
| psycopg[binary] | 3.2 | PostgreSQL driver |
| redis | 5.2 | Cache, Celery broker, sessions |
| celery | 5.4 | Async tasks, scheduled jobs |
| gunicorn | 23.x | Production WSGI server |
| whitenoise | 6.x | Static file serving |
| openai | 1.58 | AI chat integration |
| playwright | 1.48 | PDF report generation (optional) |
| pytest | 8.x | Testing |
| factory-boy | 3.3 | Test fixtures |
| ruff | 0.8 | Linting/formatting |
| mypy | 1.11 | Type checking |

### Node.js Runtime (`frontend/package.json`)

| Dependency | Version | Purpose |
|------------|---------|---------|
| Node.js | 24.x | Runtime (`.nvmrc` pinned) |
| React | 18.3 | UI framework |
| TypeScript | 5.6 | Type safety |
| Vite | 5.4 | Build tool, HMR |
| Tailwind CSS | 4.0 | Styling |
| shadcn/ui | Latest | Accessible components |
| TanStack Query | 5.x | Server state |
| Zustand | 4.x | Client state |
| React Router | 6.26 | Routing |
| Vitest | 2.x | Testing |
| ESLint + Prettier | Latest | Code quality |

### Infrastructure Services (`docker-compose.yml`)

| Service | Image | Purpose |
|---------|-------|---------|
| `web` | Built from `backend/Dockerfile` | Django + Gunicorn |
| `frontend` | Built from `frontend/Dockerfile` | Vite dev server (dev) / Nginx (prod) |
| `postgres` | `postgres:17` | Primary database |
| `redis` | `redis:7` | Cache, broker, sessions |
| `celery-worker` | Built from `backend/Dockerfile` | Async task execution |

---

## Getting Started

To get Agrivanta running locally, follow the **[Getting Started Guide](docs/getting-started.md)**. It covers:

- Docker development stack (recommended)
- Local backend/frontend development (faster iteration)
- Production-like stack
- Default credentials and first login

### Quick Start (Docker)

```bash
git clone <repository-url>
cd agrivanta
docker compose --env-file .env.dev up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000/api |
| Health Check | http://localhost:8000/healthz |
| Readiness Check | http://localhost:8000/readyz |

---

## Documentation

Detailed guides for each aspect of the project:

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Local setup, Docker, and first login |
| [Architecture](docs/architecture.md) | System design, data flows, and infrastructure |
| [API Reference](docs/api-reference.md) | Complete REST API with endpoints, parameters, and examples |
| [CI/CD & Cloud Deployment](docs/ci-cd.md) | GitHub Actions CI pipeline, CD guidance, and cloud deployment options |
| [Deployment](docs/deployment.md) | Production deployment, scaling, monitoring, and security |
| [Development](docs/development.md) | Coding standards, git workflow, testing, and common tasks |
| [Configuration](docs/configuration.md) | Environment variables for all components |
| [Project Structure](docs/project-structure.md) | Complete directory layout and module organization |
| [Database Backup & Restore](docs/database-restore.md) | Automated backup procedures and restore validation |
