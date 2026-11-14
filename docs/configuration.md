# Configuration Reference

Complete environment variable reference for all Agrivanta components.

## Quick Reference

| Component | Config File | Environment |
|-----------|-------------|-------------|
| Backend (Django) | `backend/config/settings/*.py` | `.env.dev` / `.env.prod` |
| Frontend (Vite) | `frontend/.env` | `.env` |
| Docker Compose Dev | `docker-compose.yml` | `.env.dev` |
| Docker Compose Prod | `docker-compose.prod.yml` | `.env.prod` |

---

## Backend Environment Variables

### Required for All Environments

| Variable | Description | Dev Default | Prod Required |
|----------|-------------|-------------|---------------|
| `DJANGO_SECRET_KEY` | 50+ char random string for cryptographic signing | Auto-generated | **Yes** |
| `DJANGO_DEBUG` | Enable debug mode (`1`/`0`) | `1` | `0` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed host headers | `*` | **Yes** |

### Database (PostgreSQL)

| Variable | Description | Dev Default | Prod Required |
|----------|-------------|-------------|---------------|
| `POSTGRES_DB` | Database name | `agrivanta` | **Yes** |
| `POSTGRES_USER` | Database user | `postgres` | **Yes** |
| `POSTGRES_PASSWORD` | Database password | `postgres` | **Yes** |
| `POSTGRES_HOST` | Database host | `postgres` (container) | **Yes** |
| `POSTGRES_PORT` | Database port | `5432` | `5432` |

**Note:** If PostgreSQL variables are not set, Django falls back to SQLite (`db.sqlite3`) for local development.

### Redis

| Variable | Description | Dev Default | Prod Required |
|----------|-------------|-------------|---------------|
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` | **Yes** |

### AI Chat (OpenAI-Compatible)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | API key for LLM provider | — |
| `OPENAI_MODEL` | Model identifier | `gpt-4o-mini` |
| `OPENAI_BASE_URL` | Custom endpoint (Ollama, vLLM, etc.) | `https://api.openai.com/v1` |

### Celery

| Variable | Description | Default |
|----------|-------------|---------|
| `CELERY_WORKER_CONCURRENCY` | Tasks per worker | `4` |
| `CELERY_TASK_ALWAYS_EAGER` | Run tasks synchronously (testing) | `0` |

### File Storage

**Local (Development):**
```bash
MEDIA_ROOT=/app/media
```

**AWS S3 (Production):**
```bash
AWS_STORAGE_BUCKET_NAME=agrivanta-media
AWS_S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_CUSTOM_DOMAIN=media.farm.com
AWS_DEFAULT_ACL=private
```

**Azure Blob:**
```bash
AZURE_ACCOUNT_NAME=agrivanta
AZURE_ACCOUNT_KEY=...
AZURE_CONTAINER=media
```

**Google Cloud Storage:**
```bash
GS_BUCKET_NAME=agrivanta-media
GS_PROJECT_ID=my-project
GS_CREDENTIALS=/path/to/key.json
```

### Security (Production Hardening)

| Variable | Dev | Prod | Description |
|----------|-----|------|-------------|
| `SECURE_SSL_REDIRECT` | `0` | `1` | Force HTTPS |
| `SESSION_COOKIE_SECURE` | `0` | `1` | Secure session cookies |
| `CSRF_COOKIE_SECURE` | `0` | `1` | Secure CSRF cookies |
| `SECURE_HSTS_SECONDS` | `0` | `31536000` | HSTS header (1 year) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `0` | `1` | HSTS for subdomains |
| `SECURE_HSTS_PRELOAD` | `0` | `1` | HSTS preload list |
| `CORS_ALLOWED_ORIGINS` | `*` | Your domains | CORS origins |

### Email (Production)

```bash
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=noreply@farm.com
```

### Monitoring & Observability

```bash
# Sentry
SENTRY_DSN=https://...@sentry.io/...

# Prometheus metrics
PROMETHEUS_EXPORT_MIGRATIONS=1
```

---

## Frontend Environment Variables

Create `frontend/.env` from `frontend/.env.example`:

| Variable | Values | Description |
|----------|--------|-------------|
| `VITE_API_CLIENT` | `mock` \| `http` | Service implementation |
| `VITE_API_BASE_URL` | URL string | Backend API base (required when `http`) |

**Examples:**

```bash
# Mock services (default, no backend needed)
VITE_API_CLIENT=mock

# Connect to local backend
VITE_API_CLIENT=http
VITE_API_BASE_URL=http://localhost:8000/api

# Connect to production
VITE_API_CLIENT=http
VITE_API_BASE_URL=https://api.farm.com/api
```

---

## Docker Compose Environment Files

### Development (`.env.dev`)

```bash
# .env.dev.example — copy to .env.dev and customize

# Ports (change if conflicts)
AGRIVANTA_WEB_PORT=8000
AGRIVANTA_FRONTEND_PORT=5173

# PostgreSQL
POSTGRES_DB=agrivanta
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Redis
REDIS_URL=redis://redis:6379/0

# Django
DJANGO_SECRET_KEY=dev-secret-key-change-in-production
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*

# AI (optional for development)
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

### Production (`.env.prod`)

```bash
# .env.prod.example — copy to .env.prod and fill ALL values

# Versioning
AGRIVANTA_VERSION=v1.2.3
AGRIVANTA_REVISION=abc1234

# Ports
AGRIVANTA_WEB_PORT=8000

# Workers
AGRIVANTA_WORKERS=4
AGRIVANTA_CELERY_WORKERS=2
AGRIVANTA_CELERY_CONCURRENCY=4

# Database (managed service)
POSTGRES_DB=agrivanta
POSTGRES_USER=agrivanta
POSTGRES_PASSWORD=<from-secrets-manager>
POSTGRES_HOST=db.cluster-xyz.us-east-1.rds.amazonaws.com
POSTGRES_PORT=5432

# Redis (managed service)
REDIS_URL=redis://:password@redis-cluster.xyz.use1.cache.amazonaws.com:6379

# Django (PRODUCTION VALUES REQUIRED)
DJANGO_SECRET_KEY=<50+-char-random-string>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=api.farm.com,www.farm.com

# Security
SECURE_SSL_REDIRECT=1
SESSION_COOKIE_SECURE=1
CSRF_COOKIE_SECURE=1
CORS_ALLOWED_ORIGINS=https://farm.com,https://www.farm.com

# AI
OPENAI_API_KEY=<from-secrets-manager>
OPENAI_MODEL=gpt-4o-mini

# File Storage (choose one)
# AWS_S3_...
# AZURE_...
# GS_...
```

---

## Generating Secrets

```bash
# Django secret key
python -c "import secrets; print(secrets.token_urlsafe(50))"

# Database password
openssl rand -base64 32

# API keys — use your provider's dashboard
```

---

## Configuration Precedence

1. **Environment variables** (highest) — set in shell, `.env` files, or container orchestration
2. **Docker Compose `.env` files** — `.env.dev` or `.env.prod`
3. **Dockerfile defaults** — baked into images
4. **Django settings defaults** — `config/settings/base.py`

---

## Validation Checklist

### Before Production Deploy

- [ ] `DJANGO_DEBUG=0`
- [ ] `DJANGO_SECRET_KEY` is 50+ chars, not in repo
- [ ] `DJANGO_ALLOWED_HOSTS` restricted to your domains
- [ ] `SECURE_SSL_REDIRECT=1`
- [ ] `SESSION_COOKIE_SECURE=1`
- [ ] `CSRF_COOKIE_SECURE=1`
- [ ] `CORS_ALLOWED_ORIGINS` set to frontend domain(s)
- [ ] `POSTGRES_*` point to managed database
- [ ] `REDIS_URL` points to managed Redis
- [ ] `OPENAI_API_KEY` configured
- [ ] File storage configured (S3/Azure/GCS)
- [ ] Email backend configured
- [ ] Sentry DSN configured (optional)
- [ ] All secrets in secret manager, not `.env` files