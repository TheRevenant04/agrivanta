# CI/CD & Cloud Deployment

This document describes Agrivanta's continuous integration (CI) pipeline, how to extend it into continuous delivery/deployment (CD), and how to deploy the application to cloud environments.

> **Current status:** CI is configured with GitHub Actions. There is currently **no active cloud deployment** or automated CD pipeline in this repository.

---

## Continuous Integration (CI)

CI is implemented in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) and runs on **pull requests targeting `main`**.

### Pipeline Overview

| Job | Depends on | Purpose | Key steps |
|-----|------------|---------|-----------|
| `backend` | — | Backend unit tests | Python 3.13 + `uv`, Postgres 17 service, `pytest backend/api/tests/unit` |
| `frontend` | — | Frontend quality & unit tests | Node 24, `npm ci`, `npm run lint`, `npm run build`, `vitest run src/tests/unit` |
| `verify` | `backend`, `frontend` | Integration & end-to-end tests | Build Compose stack (`docker-compose.yml` + `docker-compose.ci.yml`), backend integration tests, frontend integration tests, Playwright E2E |
| `ci-success` | `backend`, `frontend`, `verify` | Aggregated merge gate | Fails if any required job fails/cancels/is skipped |

**Recommended branch protection:** require the `CI success` status check before merging to `main`.

### Job Details

#### `backend` — Backend unit tests
- **Runner:** `ubuntu-latest`
- **Services:** `postgres:17` with health checks
- **Environment:** `POSTGRES_HOST=localhost`, `POSTGRES_PORT=5432`, `DJANGO_DEBUG=1`, test DB credentials
- **Steps:**
  1. Checkout
  2. Install `uv` (with cache)
  3. Install Python 3.13
  4. `uv sync`
  5. `uv run python -m pytest backend/api/tests/unit`

#### `frontend` — Frontend unit tests
- **Runner:** `ubuntu-latest`
- **Working directory:** `frontend/`
- **Steps:**
  1. Checkout
  2. Setup Node 24 (npm cache)
  3. `npm ci`
  4. `npm run lint`
  5. `npm run build` (TypeScript check + production build)
  6. `npx vitest run src/tests/unit`

#### `verify` — Integration and end-to-end tests
- **Runner:** `ubuntu-latest`
- **Needs:** `backend`, `frontend`
- **Environment:** local API/UI endpoints, PDF Chromium path for report tests
- **Steps:**
  1. Checkout
  2. Setup Python/uv and Node
  3. Install backend deps + PDF deps (`backend/requirements-pdf.txt`)
  4. Install frontend deps + Playwright Chromium
  5. `docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait --wait-timeout 180`
  6. Run backend integration tests (`pytest backend/api/tests/integration`) in a short bind-mounted path (Chromium socket path constraint)
  7. Run frontend integration tests (`vitest run src/tests/integration`)
  8. Run Playwright E2E tests (`npm run e2e`)
  9. **On failure:** upload `frontend/playwright-report/` artifact and dump Compose logs
  10. **Always:** tear down Compose stack (`down -v`)

### CI Artifacts & Debugging

| Artifact | When | Contents |
|----------|------|----------|
| `playwright-report` | On `verify` failure | Playwright HTML/report output (7-day retention) |
| Compose logs | On `verify` failure | `docker compose ... logs --no-color` in job output |

### Running CI Checks Locally

Run the same checks locally before opening a PR:

```bash
# Backend
uv sync
uv run python -m pytest backend/api/tests/unit

# Frontend
cd frontend
npm ci
npm run lint
npm run build
npx vitest run src/tests/unit

# Integration/E2E (requires Docker + Playwright setup)
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build
uv run pytest backend/api/tests/integration
cd frontend && npx vitest run src/tests/integration && npm run e2e
```

---

## Continuous Delivery/Deployment (CD)

CD is **not yet implemented** in this repository. The recommended approach is to extend GitHub Actions to build, publish, and deploy immutable images after changes are validated on `main`.

### Recommended CD Flow

```
Pull Request → CI (ci.yml)
      │
      │ merge to main
      ▼
Build & Publish (images tagged with SHA/version)
      │
      ▼
Deploy to Staging (automatic) → smoke/health checks
      │
      │ manual approval (recommended for production)
      ▼
Deploy to Production → health checks → monitor/rollback if needed
```

### Suggested GitHub Actions CD Workflow

Create a separate workflow (e.g. `.github/workflows/cd.yml`) triggered on pushes to `main` and/or version tags:

1. **Build**
   - Build production backend image from `docker-compose.prod.yml` / backend Dockerfile
   - Tag with commit SHA and semantic version (e.g. `ghcr.io/<org>/agrivanta-backend:<sha>`)
2. **Publish**
   - Authenticate to container registry (GHCR/ECR/ACR/GAR)
   - Push image tags
3. **Deploy to staging**
   - Apply migrations (job/one-off task)
   - Update service to new image (platform-specific)
   - Run smoke tests: `GET /healthz`, `GET /readyz`, critical API checks
4. **Promote to production** (manual approval via GitHub Environments)
   - Same deploy steps with production config/secrets
   - Monitor error rates, latency, and health checks
5. **Rollback**
   - Redeploy previous known-good image tag on failure

### Secrets & Environments

Use **GitHub Environments** (`staging`, `production`) with required reviewers for production:

| Secret / Variable | Purpose |
|-------------------|---------|
| `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` or OIDC role | Push images to registry |
| `DJANGO_SECRET_KEY` | Production Django secret |
| `POSTGRES_*` / `REDIS_URL` | Managed data services |
| `OPENAI_API_KEY` | AI chat provider |
| Cloud credentials / OIDC role | Deploy to target platform (AWS/Azure/GCP) |

**Best practices:**
- Prefer OIDC/workload identity federation over long-lived cloud keys
- Never commit `.env.prod` secrets; inject via platform secret managers
- Run migrations as a controlled step before/with rollout (see [Deployment Guide](deployment.md#database-setup))

### Deployment Gates

- All CI checks (`CI success`) must pass before merge
- Staging deploy should run automated smoke tests
- Production deploy should require manual approval and post-deploy verification
- Keep rollback to previous image tag documented and tested

---

## Cloud Deployment (No Active Cloud Deployment)

Agrivanta is containerized and can be deployed to major cloud providers. The production-like Compose stack (`docker-compose.prod.yml`) defines the runtime shape; managed services should replace containerized Postgres/Redis in production.

### Common Cloud Architecture

- **Compute:** container service (ECS/AKS/GKE/Cloud Run/App Service/Container Apps)
- **Database:** managed PostgreSQL (RDS/Azure Database/Cloud SQL)
- **Cache/Broker:** managed Redis (ElastiCache/Azure Cache/Memorystore)
- **Object storage:** S3/Azure Blob/GCS for media and attachments
- **Networking:** load balancer + TLS, private networking for DB/Redis
- **Secrets:** cloud secret manager + CI/CD environment secrets
- **Observability:** centralized logs, metrics, tracing, alerts

### Option 1: AWS (ECS Fargate + RDS + ElastiCache)

**Good for:** managed containers without Kubernetes operations.

1. **Provision infrastructure**
   - VPC with public (ALB) and private (tasks, DB, Redis) subnets
   - RDS PostgreSQL 17, ElastiCache Redis 7, S3 bucket for media
   - ECR repository for images, ACM certificate, ALB
2. **Configure application**
   - Store secrets in AWS Secrets Manager/SSM
   - Set env vars per [Configuration Reference](configuration.md)
3. **Deploy**
   - Push image to ECR
   - Create ECS task definitions/services for web and Celery worker
   - Run migrations as a one-off ECS task
   - Point ALB to ECS service; verify `/healthz` and `/readyz`
4. **Operate**
   - CloudWatch logs/alarms, autoscaling policies, automated RDS backups

### Option 2: Azure (Container Apps or AKS + Azure Database for PostgreSQL + Azure Cache for Redis)

**Good for:** Azure-native managed containers or Kubernetes.

1. **Provision infrastructure**
   - Resource group, Container Apps Environment or AKS cluster
   - Azure Database for PostgreSQL Flexible Server, Azure Cache for Redis
   - Azure Blob Storage, Azure Container Registry, Key Vault
2. **Configure application**
   - Store secrets in Key Vault; inject into Container Apps/AKS
   - Set env vars and storage settings per [Configuration Reference](configuration.md)
3. **Deploy**
   - Push image to ACR
   - Deploy web and worker containers; run migration job
   - Configure ingress/TLS and health probes (`/healthz`, `/readyz`)
4. **Operate**
   - Azure Monitor/Log Analytics, scaling rules, backup policies

### Option 3: GCP (Cloud Run or GKE + Cloud SQL + Memorystore)

**Good for:** serverless containers (Cloud Run) or Kubernetes (GKE).

1. **Provision infrastructure**
   - Cloud SQL for PostgreSQL, Memorystore for Redis, GCS bucket
   - Artifact Registry, load balancer/HTTPS, Secret Manager
2. **Configure application**
   - Use Secret Manager for credentials
   - For Cloud SQL, use Cloud SQL Auth Proxy/connector as appropriate
3. **Deploy**
   - Push image to Artifact Registry
   - Deploy web service and worker (Cloud Run service/job or GKE Deployments)
   - Run migrations before traffic cutover
4. **Operate**
   - Cloud Logging/Monitoring, autoscaling, automated backups

### Option 4: Kubernetes (Cloud-Agnostic)

Use the Kubernetes guidance in the [Deployment Guide](deployment.md#kubernetes-recommended-for-scale) as a baseline. For any managed Kubernetes (EKS/AKS/GKE):

- Use a managed Ingress/controller with TLS
- Store secrets in External Secrets/Secrets Store CSI + cloud secret manager
- Use HPA for web/worker scaling
- Run migrations via Job/Helm hook/init workflow (with care for rolling deploys)
- Prefer managed PostgreSQL/Redis outside the cluster

### Production Readiness Checklist (Cloud)

- [ ] CI passing (`CI success`) and image built from a known commit
- [ ] Managed PostgreSQL and Redis provisioned with backups/HA as needed
- [ ] Object storage configured for media/attachments
- [ ] Secrets stored in secret manager (no plaintext in repo/manifests)
- [ ] TLS, security headers, and WAF/rate limiting configured
- [ ] Health checks wired to `/healthz` and `/readyz`
- [ ] Migrations, rollback, and restore procedures tested
- [ ] Monitoring, alerting, and log retention configured

## Related Documentation

- [Deployment Guide](deployment.md) — Docker, Kubernetes, reverse proxy, operations
- [Configuration Reference](configuration.md) — Environment variables and secrets
- [Development Guide](development.md) — Local workflows and contribution process
- [Database Backup & Restore](database-restore.md) — Backup and recovery procedures
