# Deployment Guide

This guide covers deploying Agrivanta to production environments.

> **Current status:** There is no active cloud deployment for this project. See [CI/CD & Cloud Deployment](ci-cd.md) for the GitHub Actions CI pipeline, CD guidance, and cloud deployment options.

## Prerequisites

- **Docker Engine** 24+ with Compose v2 plugin
- **PostgreSQL 17** (managed service recommended: AWS RDS, Azure Database, Google Cloud SQL)
- **Redis 7** (managed service recommended: AWS ElastiCache, Azure Cache, Google Memorystore)
- **Object Storage** for media/attachments (S3, GCS, Azure Blob)
- **SSL/TLS Certificates** (Let's Encrypt or managed)
- **Domain Name** with DNS configured
- **Container Registry** (GitHub Container Registry, Docker Hub, ECR, etc.)

## Architecture Overview

```
                    ┌─────────────────┐
                    │  Load Balancer  │  (SSL termination, WAF)
                    │  (nginx/ALB)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │ Backend 1 │  │ Backend 2 │  │ Backend N │  (Gunicorn workers)
        └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │  Celery   │  │  Celery   │  │  Celery   │  (Workers)
        │ Worker 1  │  │ Worker 2  │  │ Worker N  │
        └───────────┘  └───────────┘  └───────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │PostgreSQL │  │   Redis   │  │  Object   │
        │ (Primary) │  │ (Cluster) │  │  Storage  │
        └───────────┘  └───────────┘  └───────────┘
```

## Environment Variables

See the **[Configuration Reference](configuration.md)** for the complete environment variable reference. The essentials for production:

### Required (Production)

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | 50+ char random string | `generated-with-openssl` |
| `DJANGO_DEBUG` | Must be `0` | `0` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated domains | `api.farm.com,www.farm.com` |
| `POSTGRES_DB` | Database name | `agrivanta` |
| `POSTGRES_USER` | Database user | `agrivanta` |
| `POSTGRES_PASSWORD` | Strong password | `from-secrets-manager` |
| `POSTGRES_HOST` | Database host | `db.cluster-xyz.us-east-1.rds.amazonaws.com` |
| `POSTGRES_PORT` | Database port | `5432` |
| `REDIS_URL` | Redis connection URL | `redis://:password@redis-cluster.xyz.use1.cache.amazonaws.com:6379` |
| `OPENAI_API_KEY` | For AI chat | `sk-...` |
| `OPENAI_MODEL` | Model to use | `gpt-4o-mini` |

### Production Hardening (Required)

| Variable | Value | Description |
|----------|-------|-------------|
| `SECURE_SSL_REDIRECT` | `1` | Force HTTPS |
| `SESSION_COOKIE_SECURE` | `1` | Secure session cookies |
| `CSRF_COOKIE_SECURE` | `1` | Secure CSRF cookies |
| `CORS_ALLOWED_ORIGINS` | Your domains | Comma-separated frontend origins |

### Media Storage (choose one)

See [Configuration Reference](configuration.md#file-storage) for complete S3, Azure Blob, and GCS setup.

## Docker Images

### Build Locally
```bash
# Tag with version
export AGRIVANTA_VERSION=v1.2.3
export AGRIVANTA_REVISION=$(git rev-parse --short HEAD)

docker compose -f docker-compose.prod.yml build
```

### Push to Registry
```bash
docker tag agrivanta-backend:${AGRIVANTA_VERSION} ghcr.io/yourorg/agrivanta-backend:${AGRIVANTA_VERSION}
docker push ghcr.io/yourorg/agrivanta-backend:${AGRIVANTA_VERSION}
```

## Database Setup

### Initial Migration
```bash
# Run migrations on new database
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Create superuser
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser

# Collect static files
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
```

### Ongoing Migrations
```bash
# Apply new migrations (zero-downtime with proper ordering)
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --plan
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
```

## Running in Production

### Docker Compose (Single Host)
```bash
# Create production env file
cp .env.prod.example .env.prod
# Edit .env.prod with all secrets

# Start services
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d

# Verify health
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/readyz
```

### Kubernetes (Recommended for Scale)

**Key Resources:**
- `Deployment` for backend (replicas: 3+)
- `Deployment` for Celery workers (replicas: 2+)
- `Service` for backend (ClusterIP)
- `Ingress` with TLS
- `ConfigMap` for non-secret config
- `Secret` for credentials
- `PersistentVolumeClaim` for media (if not using object storage)
- `HorizontalPodAutoscaler` for backend and workers

**Example Backend Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agrivanta-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agrivanta-backend
  template:
    spec:
      containers:
      - name: web
        image: ghcr.io/yourorg/agrivanta-backend:v1.2.3
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: agrivanta-config
        - secretRef:
            name: agrivanta-secrets
        readinessProbe:
          httpGet:
            path: /readyz
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

## Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name api.farm.com;

    ssl_certificate /etc/letsencrypt/live/api.farm.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.farm.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header Referrer-Policy strict-origin-when-cross-origin;

    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for future features
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files served by WhiteNoise, but can offload to CDN
    location /static/ {
        alias /app/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /app/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
}
```

## SSL/TLS

**Let's Encrypt (Certbot):**
```bash
certbot --nginx -d api.farm.com -d www.farm.com
```

**Auto-renewal:**
```bash
# systemd timer or cron
0 3 * * * certbot renew --quiet --post-hook "nginx -s reload"
```

## Monitoring & Observability

### Health Checks
- **Liveness**: `GET /healthz` — Process alive
- **Readiness**: `GET /readyz` — DB + Redis + migrations current

### Logging
```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f web

# Structured JSON logs (production)
# Configure in settings/production.py:
LOGGING = {
    'version': 1,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json'
        }
    },
    'root': {'handlers': ['console'], 'level': 'INFO'}
}
```

### Metrics (Prometheus)
```bash
# Add to requirements
pip install django-prometheus

# Expose /metrics endpoint
# Configure Prometheus to scrape
```

### Error Tracking (Sentry)
```bash
# Add to requirements
pip install sentry-sdk[django]

# In settings/production.py
import sentry_sdk
sentry_sdk.init(
    dsn="https://...@sentry.io/...",
    traces_sample_rate=0.1,
    profiles_sample_rate=0.1,
)
```

## Backup & Disaster Recovery

See [Database Backup and Restore](database-restore.md) for detailed procedures.

**Automated Backup (cron/systemd):**
```bash
# Daily at 02:00 UTC
0 2 * * * /usr/local/bin/backup-postgresql.sh
```

**Recovery Objectives:**
- RPO: 24 hours (daily backups)
- RTO: < 1 hour (tested monthly)

## Scaling Guidelines

| Component | Scaling Trigger | Action |
|-----------|-----------------|--------|
| Backend | CPU > 70%, latency > 500ms | Add replicas |
| Celery Workers | Queue depth > 100 | Add workers |
| PostgreSQL | Connections > 80% | Upgrade instance / PgBouncer |
| Redis | Memory > 80% | Upgrade / Cluster mode |

## Security Checklist

- [ ] `DJANGO_DEBUG=0`
- [ ] Strong `DJANGO_SECRET_KEY` (rotate annually)
- [ ] `DJANGO_ALLOWED_HOSTS` restricted to your domains
- [ ] HTTPS enforced (`SECURE_SSL_REDIRECT=1`)
- [ ] Secure cookies (`SESSION_COOKIE_SECURE=1`, `CSRF_COOKIE_SECURE=1`)
- [ ] Database not publicly accessible (VPC/private subnet)
- [ ] Redis not publicly accessible
- [ ] Secrets in secret manager, not env files
- [ ] Regular security updates (base images, dependencies)
- [ ] WAF rules for API endpoints
- [ ] Rate limiting configured
- [ ] Audit logging enabled

## Rollback Procedure

```bash
# 1. Tag current version
export PREVIOUS_VERSION=v1.2.2

# 2. Update image tag in .env.prod
sed -i "s/AGRIVANTA_VERSION=.*/AGRIVANTA_VERSION=${PREVIOUS_VERSION}/" .env.prod

# 3. Deploy previous version
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

# 4. Verify health
curl -f http://localhost:8000/healthz
curl -f http://localhost:8000/readyz

# 5. If DB migration was applied, run reverse migration
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm web python manage.py migrate <app> <previous_migration>
```

## Maintenance Windows

- **Weekly**: Dependency updates, security patches
- **Monthly**: Backup restore test, log review
- **Quarterly**: Capacity planning, DR drill
- **Annually**: Secret rotation, certificate renewal, penetration test

## CI/CD & Cloud Deployment

For the repository's GitHub Actions CI pipeline, recommended CD flow, and cloud deployment options (AWS, Azure, GCP, Kubernetes), see **[CI/CD & Cloud Deployment](ci-cd.md)**.