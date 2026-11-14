# Development Guide

This guide covers local development workflows, coding standards, and contribution practices for Agrivanta.

## Quick Start

```bash
# Clone and enter
git clone <repository-url>
cd agrivanta

# Option 1: Full Docker stack (recommended)
docker compose --env-file .env.dev up --build

# Option 2: Local services (faster iteration)
# Terminal 1 - Backend
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py runserver

# Terminal 2 - Frontend
cd frontend && npm ci && npm run dev
```

## Development Environment

### Backend (Django)

**Requirements:**
- Python 3.13+
- `uv` package manager
- PostgreSQL 17 (via Docker) or SQLite (default)

**Key Commands:**
```bash
cd backend

# Install dependencies
uv sync

# Database
uv run python manage.py migrate              # Apply migrations
uv run python manage.py makemigrations       # Create new migrations
uv run python manage.py showmigrations       # Check status

# Development server
uv run python manage.py runserver            # http://localhost:8000

# Testing
uv run pytest                                # All tests
uv run pytest -k "test_name"                 # Specific test
uv run pytest --cov=api                      # With coverage

# Code quality
uv run ruff check .                          # Lint
uv run ruff format .                         # Format
uv run mypy .                                # Type check

# Django utilities
uv run python manage.py shell                # Django shell
uv run python manage.py collectstatic        # Collect static files
uv run python manage.py createsuperuser      # Admin user
```

**Settings Files:**
- `config/settings/base.py` — Shared configuration
- `config/settings/development.py` — Local development (DEBUG=True)
- `config/settings/production.py` — Production hardened settings

### Frontend (React + Vite)

**Requirements:**
- Node.js 24.x (use `nvm use` from `frontend/`)
- npm

**Key Commands:**
```bash
cd frontend

# Install
npm ci

# Development
npm run dev              # http://localhost:5173 (HMR)
npm run dev -- --host    # Accessible on network

# Build & Preview
npm run build            # Type-check + production build to dist/
npm run preview          # Serve dist/ locally

# Code Quality
npm run lint             # ESLint (errors = fail)
npm run format           # Prettier write
npm run format:check     # Prettier check (CI)

# Testing
npm run test             # Vitest (single run, CI-friendly)
npm run test -- --watch  # Watch mode

# API Client Generation
npm run api:generate     # Regenerate from backend OpenAPI spec
```

**Environment Variables (`frontend/.env`):**
```bash
# Mock services (default, no backend needed)
VITE_API_CLIENT=mock

# HTTP client (connects to backend)
VITE_API_CLIENT=http
VITE_API_BASE_URL=http://localhost:8000/api
```

## Project Structure

### Backend
```
backend/
├── api/                      # Main API app
│   ├── models/               # Domain models
│   ├── views/                # ViewSets (DRF)
│   ├── serializers/          # Serializers
│   ├── permissions/          # Custom permissions
│   ├── filters/              # FilterSets
│   ├── exports/              # PDF/Excel/CSV export
│   ├── ai/                   # AI chat integration
│   │   ├── tools/            # Function-calling tools
│   │   └── prompts/          # System prompts
│   ├── management/commands/  # Custom CLI commands
│   └── tests/                # Test suites
├── config/                   # Django project config
│   └── settings/
│       ├── base.py
│       ├── development.py
│       └── production.py
├── media/                    # Uploads (gitignored)
├── static/                   # Collected static (gitignored)
├── manage.py
├── pyproject.toml            # Project metadata, deps
└── uv.lock                   # Locked dependencies
```

### Frontend
```
frontend/
├── src/
│   ├── app/                  # App shell, routing, providers
│   ├── components/
│   │   ├── ui/               # shadcn/ui primitives
│   │   └── ...               # Feature components
│   ├── pages/                # Route-level components
│   ├── services/             # Typed API layer
│   │   ├── types.ts          # Service contract
│   │   ├── httpServices.ts
│   │   ├── mockServices.ts
│   │   └── generated/        # OpenAPI-generated types
│   ├── hooks/                # Custom hooks
│   ├── stores/               # Zustand stores
│   ├── lib/                  # Utilities
│   └── styles/               # Global styles, theme
├── public/                   # Static assets
├── dist/                     # Production build (gitignored)
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── components.json           # shadcn/ui config
└── .env.example
```

## Coding Standards

### Python (Backend)

**Style:** Ruff (PEP 8 + modern conventions)
```bash
# Auto-format
uv run ruff format .

# Check only
uv run ruff check .
```

**Type Hints:** Required for all public functions
```python
def calculate_profitability(crop_cycle_id: UUID) -> ProfitabilityResult:
    ...
```

**Imports:** Absolute imports, grouped (stdlib, third-party, local)
```python
import uuid
from datetime import date

from django.db import models
from rest_framework import serializers

from api.models import CropCycle
from api.services.profitability import calculate_profitability
```

**Testing:** Pytest with fixtures
```python
# backend/api/tests/unit/test_profitability.py
import pytest
from api.services.profitability import calculate_profitability

@pytest.mark.django_db
def test_profitability_calculation(farm, crop_cycle, expenses, harvests):
    result = calculate_profitability(crop_cycle.id)
    assert result.gross_revenue > 0
    assert result.net_profit == result.gross_revenue - result.total_costs
```

### TypeScript (Frontend)

**Style:** ESLint + Prettier (configured)
```bash
# Auto-format
npm run format

# Check only
npm run format:check
npm run lint
```

**Type Safety:** Strict mode enabled, no `any`
```typescript
// Good
interface HarvestData {
  cropCycleId: string;
  quantity: number;
  unitId: string;
}

// Avoid
const data: any = fetchHarvest();
```

**Component Pattern:** Function components with hooks
```tsx
// components/harvest/HarvestForm.tsx
import { useForm } from 'react-hook-form';
import { useServices } from '@/services/servicesContext';

export function HarvestForm({ cropCycleId }: { cropCycleId: string }) {
  const { harvests } = useServices();
  const { register, handleSubmit } = useForm<HarvestData>();

  const onSubmit = async (data: HarvestData) => {
    await harvests.create({ ...data, cropCycleId });
  };

  return <form onSubmit={handleSubmit(onSubmit)}>...</form>;
}
```

**Services Layer:** All backend access through contract
```typescript
// services/types.ts
export interface AgrivantaServices {
  harvests: HarvestService;
  expenses: ExpenseService;
  // ...
}

// Usage in components
const { harvests } = useServices();
const data = await harvests.list({ cropCycleId });
```

## Git Workflow

### Branching Strategy
```
main (protected)
  │
  ├── feature/farm-onboarding-wizard
  ├── fix/profitability-calculation-rounding
  ├── docs/api-reference-update
  └── refactor/services-layer-types
```

**Branch Naming:** `<type>/<short-description>`
- `feature/` — New functionality
- `fix/` — Bug fixes
- `docs/` — Documentation only
- `refactor/` — Code restructuring
- `test/` — Test additions
- `ci/` — CI/CD changes
- `build/` — Build system changes
- `chore/` — Maintenance

### Commit Messages (Conventional Commits)

```
<type>[scope][!]: <imperative description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `build`, `chore`, `perf`, `security`

**Examples:**
```bash
feat(activities): add activity completion endpoint
fix(profitability): correct overhead allocation rounding
docs(api): update chat endpoint documentation
refactor(services): extract HTTP client to separate module
test(reports): add yield comparison test cases
```

**Rules:**
- ≤ 72 characters subject line
- Lowercase start, no trailing period
- Imperative mood ("add" not "added")
- No vague subjects ("update code")
- Reference issues in body/footer if applicable

### Pull Request Process

1. **Create branch** from `main`
2. **Develop** with atomic commits
3. **Run checks** locally:
   ```bash
   # Backend
   cd backend && uv run pytest && uv run ruff check . && uv run mypy .
   
   # Frontend
   cd frontend && npm run test && npm run lint && npm run format:check
   ```
4. **Push branch** and open PR
5. **CI runs** — GitHub Actions validates unit, integration, and E2E checks on PRs to `main` (see [CI/CD & Cloud Deployment](ci-cd.md))
6. **Code review** — address feedback
7. **Squash merge** to `main` (maintains clean history)

## Testing Strategy

### Backend Tests
```
backend/api/tests/
├── unit/              # Fast, isolated tests
│   ├── test_models.py
│   ├── test_serializers.py
│   └── test_services/
├── integration/       # Database, API tests
│   ├── test_views.py
│   ├── test_permissions.py
│   └── test_database_backup_restore.py
└── fixtures/          # Shared test data
```

**Run:**
```bash
uv run pytest                          # All
uv run pytest backend/api/tests/unit/  # Unit only
uv run pytest -x                       # Stop on first failure
uv run pytest --cov=api --cov-report=html  # Coverage report
```

### Frontend Tests
```
frontend/src/
├── **/*.test.tsx       # Component tests (Vitest + RTL)
├── **/*.test.ts        # Utility/service tests
└── setupTests.ts       # Test configuration
```

**Run:**
```bash
npm run test              # Single run (CI)
npm run test -- --watch   # Watch mode
npm run test -- --ui      # Vitest UI
```

### Test Data

**Backend:** Factory Boy fixtures in `tests/factories.py`
```python
# tests/factories.py
import factory
from api.models import CropCycle, Field

class FieldFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Field
    name = factory.Sequence(lambda n: f"Field {n}")
    area_hectares = 10.5
    farm = factory.SubFactory(FarmFactory)
```

**Frontend:** Mock services with seed data in `services/mockServices.ts`

## Common Tasks

### Adding a New Model

1. Create model in `api/models/<domain>.py`
2. Create serializer in `api/serializers/<domain>.py`
3. Create viewset in `api/views/<domain>.py`
4. Register routes in `api/urls.py`
5. Add filters in `api/filters/<domain>.py`
6. Create tests in `api/tests/unit/test_<domain>.py` and `api/tests/integration/test_<domain>_views.py`
7. Generate migration: `uv run python manage.py makemigrations`
8. Run migration: `uv run python manage.py migrate`
9. Update OpenAPI spec (auto on server restart)
10. Regenerate frontend types: `cd frontend && npm run api:generate`

### Adding an AI Tool

1. Create tool in `api/ai/tools/<name>.py`
2. Register in `api/ai/tools/__init__.py`
3. Add system prompt context in `api/ai/prompts/system.md`
4. Write integration test in `api/tests/integration/test_ai_tools.py`
5. Test manually via chat UI

### Adding a Report Export

1. Create exporter in `api/exports/<name>.py`
2. Register in `api/exports/__init__.py`
3. Add endpoint in `api/views/reports.py`
4. Add frontend export button in `components/reports/ReportToolbar.tsx`
5. Test PDF/Excel/CSV generation

## Debugging

### Backend
```bash
# Django shell with context
uv run python manage.py shell_plus

# Debug specific request
# Add breakpoint() in code, then:
uv run python manage.py runserver --nothreading

# SQL queries
# Set DEBUG=True, check django.db.connection.queries
```

### Frontend
```bash
# React DevTools (browser extension)
# Redux DevTools (if using)

# Network tab for API calls
# Console for React warnings

# Vite HMR issues
npm run dev -- --force
```

### Database
```bash
# Direct PostgreSQL access (Docker)
docker compose exec postgres psql -U postgres -d agrivanta

# Django dbshell
uv run python manage.py dbshell
```

## Performance Profiling

### Backend
```bash
# Django Debug Toolbar (development only)
# Add to INSTALLED_APPS in development.py

# SQL query count
# Check django.db.connection.queries in shell

# Profiling
pip install pyinstrument
pyinstrument -m pytest backend/api/tests/...
```

### Frontend
```bash
# React Profiler (DevTools)
# Lighthouse (Chrome DevTools)
# Bundle analyzer
npm run build && npx vite-bundle-analyzer dist
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `uv sync` fails | Check Python version (3.13+), `uv self update` |
| Migrations conflict | `uv run python manage.py migrate --fake-initial` |
| Frontend not connecting to backend | Check `VITE_API_BASE_URL`, CORS settings |
| AI chat not working | Verify `OPENAI_API_KEY` in backend env |
| Docker build fails | `docker compose build --no-cache` |
| Port conflicts | Change `AGRIVANTA_WEB_PORT` or `AGRIVANTA_FRONTEND_PORT` |
| Tests flaky | Check test isolation, database transactions |

## Useful Resources

- [Django REST Framework Docs](https://www.django-rest-framework.org/)
- [React 18 Docs](https://react.dev/)
- [Tailwind CSS v4 Docs](https://tailwindcss.com/docs)
- [shadcn/ui Components](https://ui.shadcn.com/)
- [Vitest Docs](https://vitest.dev/)
- [OpenAPI Generator](https://openapi-generator.tech/)
- [Conventional Commits](https://www.conventionalcommits.org/)

## Related Documentation

- [CI/CD & Cloud Deployment](ci-cd.md) — GitHub Actions CI pipeline and cloud deployment guidance
- [Configuration Reference](configuration.md) — All environment variables
- [Project Structure](project-structure.md) — Complete directory layout
- [Architecture](architecture.md) — System design and data flows
- [API Reference](api-reference.md) — REST API endpoints