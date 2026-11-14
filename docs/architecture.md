# System Architecture

Agrivanta is a modern, cloud-native web application built with a decoupled frontend and backend architecture.

## High-Level Architecture

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

## Frontend Architecture

**Technology Stack:**
- **React 18** with TypeScript
- **Vite** for build tooling and HMR
- **Tailwind CSS v4** for styling
- **shadcn/ui** for accessible component primitives
- **React Router 7** for routing
- **TanStack Query** for server state management
- **Vitest** + React Testing Library for testing

**Project Structure:**
```
frontend/
├── src/
│   ├── app/              # App shell, routing, providers
│   ├── components/       # Reusable UI components
│   │   ├── ui/           # shadcn/ui primitives
│   │   └── ...           # Feature components
│   ├── pages/            # Route-level components
│   ├── services/         # Typed API client layer
│   │   ├── types.ts      # Service contract (interface)
│   │   ├── httpServices.ts
│   │   ├── mockServices.ts
│   │   └── generated/    # OpenAPI-generated types
│   ├── hooks/            # Custom React hooks
│   ├── stores/           # Client state (Zustand)
│   ├── lib/              # Utilities
│   └── styles/           # Global styles, theme
├── public/               # Static assets
└── dist/                 # Production build output
```

**Key Patterns:**
- **Services Layer**: All backend access through `AgrivantaServices` contract — no direct fetch/axios in components
- **Mock-First Development**: Full in-memory mock implementation for offline development
- **OpenAPI-Driven**: Types and DTOs generated from backend schema
- **Streaming Chat**: Custom NDJSON transport for AI chat (bypasses generated client)

## Backend Architecture

**Technology Stack:**
- **Django 5.2** + **Django REST Framework**
- **PostgreSQL 17** (production) / SQLite (local dev default)
- **Redis 7** for caching, Celery broker, and sessions
- **Celery** for async tasks and scheduled jobs
- **Gunicorn** for production WSGI server
- **WhiteNoise** for static file serving
- **pytest** for testing

**Project Structure:**
```
backend/
├── api/                  # Main API application
│   ├── models/           # Database models
│   ├── views/            # API viewsets
│   ├── serializers/      # DRF serializers
│   ├── permissions/      # Custom permission classes
│   ├── filters/          # Django-filter filtersets
│   ├── pagination/       # Custom pagination
│   ├── exports/          # PDF/Excel/CSV export utilities
│   ├── ai/               # AI chat integration
│   │   ├── tools/        # Function-calling tools
│   │   └── prompts/      # System prompts
│   ├── management/       # Custom management commands
│   └── tests/            # Test suites
├── config/               # Django settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   └── urls.py
├── media/                # User uploads (gitignored)
├── static/               # Collected static files
└── manage.py
```

**Core Domain Models:**
- **Farm** → **Fields** → **Crop Cycles** (per field, overlapping supported)
- **Crops** / **Varieties** / **Units** / **Conversions**
- **Activities** (planned/in-progress/completed/overdue) with **Templates**
- **Inventory Items** → **Stock Movements** (purchases, usage, adjustments)
- **Expenses** / **Payments** / **Budgets** (crop-cycle and category level)
- **Harvests** / **Sales** / **Customers** / **Suppliers**
- **Seasons** / **Reporting Periods** (calendar and agricultural)
- **Notifications** (overdue activities, low stock, budget overruns)
- **Attachments** (receipts, invoices linked to transactions)

## Data Flow

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

## Infrastructure

### Development (docker-compose.yml)
- Bind-mounted source for auto-reload
- Django runserver + Vite dev server
- PostgreSQL + Redis in containers
- Celery worker (no beat scheduler)

### Production-like (docker-compose.prod.yml)
- Multi-stage Dockerfile (build → runtime)
- Gunicorn + WhiteNoise
- Non-root user (UID 10001)
- Immutable images with version tags
- Named volumes for PostgreSQL, media, attachments
- Restart policy: `unless-stopped`

### Environment Configuration
| Environment | Config File | Purpose |
|-------------|-------------|---------|
| Development | `.env.dev` | Local overrides for dev stack |
| Production | `.env.prod` | Secrets, image tags, worker counts |
| Backend Settings | `config/settings/*.py` | Django settings per environment |

## Security

- **Authentication**: JWT-based (access/refresh tokens)
- **Authorization**: Role-based (Owner, Manager, Worker) + object-level permissions
- **API**: CORS restricted, rate limiting ready
- **Secrets**: Never committed; loaded from environment
- **Database**: Prepared statements, parameterized queries
- **AI**: Read-only tools, no data mutation, evidence citations

## Observability

- **Health Endpoints**: `/healthz` (liveness), `/readyz` (readiness + DB)
- **Structured Logging**: JSON format in production
- **Error Tracking**: Ready for Sentry integration
- **Metrics**: Prometheus-compatible `/metrics` endpoint (planned)

## Related Documentation

- [Project Structure](project-structure.md) — Complete directory layout and modules
- [Configuration](configuration.md) — All environment variables
- [Deployment](deployment.md) — Production infrastructure
- [Development](development.md) — Coding standards and workflows