# Database Backup and Restore Procedure

## Overview

This document describes the PostgreSQL backup and restore procedures for Agrivanta. The database uses automated daily backups via `pg_dump` with verification capability. Regular restore validation ensures backups are reliable and restore procedures are well-tested.

## Backup Strategy

### Automated Backup Setup

**Tool:** PostgreSQL `pg_dump` command
**Frequency:** Daily (recommended 02:00 UTC)
**Retention:** 30 days of daily backups
**Storage:** Local backup directory (production: cloud storage recommended)

### Backup Location

```
/backups/agrivanta/postgresql/
  ├── agrivanta-2026-11-05.sql.gz
  ├── agrivanta-2026-11-04.sql.gz
  └── agrivanta-2026-11-03.sql.gz
```

### Backup Artifact Naming Convention

- Format: `agrivanta-YYYY-MM-DD.sql.gz`
- Compressed with gzip
- Metadata file: `agrivanta-YYYY-MM-DD.sql.gz.txt`

### Backup Script

#### Password Configuration

PostgreSQL commands require database credentials. Choose one of these methods:

**Option 1: .pgpass file (recommended for automation)**

Create `~/.pgpass` with database credentials:
```
hostname:port:database:username:password
localhost:5432:agrivanta:postgres:your_password
```

Make it secure:
```bash
chmod 600 ~/.pgpass
```

**Option 2: Environment variable**

```bash
export PGPASSWORD="your_password"
pg_dump --host="$DB_HOST" --username="$DB_USER" --dbname="$DB_NAME" | gzip > backup.sql.gz
```

**Option 3: Prompt for password**

Add `-W` flag to prompt interactively (not suitable for automated jobs):
```bash
pg_dump -W --host="$DB_HOST" --username="$DB_USER" --dbname="$DB_NAME"
```

#### Backup Script with Password Handling

Create `/usr/local/bin/backup-postgresql.sh`:

```bash
#!/bin/bash
set -e

# Configuration
DB_NAME="agrivanta"
DB_USER="postgres"
DB_HOST="localhost"
BACKUP_DIR="/backups/agrivanta/postgresql"
RETENTION_DAYS=30
DATE=$(date +%Y-%m-%d)

mkdir -p "$BACKUP_DIR"

# Ensure .pgpass is configured (or use PGPASSWORD environment variable)
# See Password Configuration section above

# Create backup
pg_dump --host="$DB_HOST" --username="$DB_USER" --dbname="$DB_NAME" \
  | gzip > "$BACKUP_DIR/agrivanta-$DATE.sql.gz"

# Verify integrity
gzip -t "$BACKUP_DIR/agrivanta-$DATE.sql.gz"

# Store metadata
{
  echo "Backup Date: $(date)"
  echo "Database: $DB_NAME"
  echo "Size: $(du -h "$BACKUP_DIR/agrivanta-$DATE.sql.gz" | cut -f1)"
} > "$BACKUP_DIR/agrivanta-$DATE.sql.gz.txt"

# Clean old backups
find "$BACKUP_DIR" -name "agrivanta-*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "✓ Backup completed: agrivanta-$DATE.sql.gz"
```

Enable as systemd timer or cron job:

```bash
chmod +x /usr/local/bin/backup-postgresql.sh

# Option 1: Cron (run daily at 02:00 UTC)
# 0 2 * * * /usr/local/bin/backup-postgresql.sh >> /var/log/postgresql-backup.log 2>&1

# Option 2: systemd timer (recommended)
# Create /etc/systemd/system/postgresql-backup.timer with OnCalendar=*-*-* 02:00:00
```

---

## Restore Procedure

### Step 1: Prepare Scratch Database

```bash
sudo -u postgres psql -c "CREATE DATABASE agrivanta_restore_test;"
```

### Step 2: Decompress and Restore

```bash
cd /backups/agrivanta/postgresql

# Decompress
gunzip -c agrivanta-2026-11-05.sql.gz > agrivanta-2026-11-05.sql

# Restore to scratch database
psql --username=postgres --dbname=agrivanta_restore_test \
  --file=agrivanta-2026-11-05.sql
```

### Step 3: Verify Row Counts

Connect to restored database and verify core tables:

```bash
psql --username=postgres --dbname=agrivanta_restore_test << 'EOF'
\x
SELECT 'auth_user' as table_name, COUNT(*) FROM auth_user
UNION ALL
SELECT 'api_farm', COUNT(*) FROM api_farm
UNION ALL
SELECT 'api_field', COUNT(*) FROM api_field
UNION ALL
SELECT 'api_crop', COUNT(*) FROM api_crop
UNION ALL
SELECT 'api_variety', COUNT(*) FROM api_variety
UNION ALL
SELECT 'api_activity', COUNT(*) FROM api_activity
UNION ALL
SELECT 'api_activitytype', COUNT(*) FROM api_activitytype
UNION ALL
SELECT 'api_inventoryitem', COUNT(*) FROM api_inventoryitem
UNION ALL
SELECT 'api_stockmovement', COUNT(*) FROM api_stockmovement
UNION ALL
SELECT 'api_expense', COUNT(*) FROM api_expense
UNION ALL
SELECT 'api_supplier', COUNT(*) FROM api_supplier
UNION ALL
SELECT 'api_customer', COUNT(*) FROM api_customer
UNION ALL
SELECT 'api_season', COUNT(*) FROM api_season
UNION ALL
SELECT 'api_reportingperiod', COUNT(*) FROM api_reportingperiod
ORDER BY table_name;
EOF
```

**Record the row counts here for comparison with source:**

| Table | Count |
|-------|-------|
| auth_user | _____ |
| api_farm | _____ |
| api_field | _____ |
| api_crop | _____ |
| api_variety | _____ |
| api_activity | _____ |
| api_activitytype | _____ |
| api_inventoryitem | _____ |
| api_stockmovement | _____ |
| api_expense | _____ |
| api_supplier | _____ |
| api_customer | _____ |
| api_season | _____ |
| api_reportingperiod | _____ |

### Step 4: Production Restore (if needed)

```bash
# 1. Stop application
systemctl stop agrivanta

# 2. Safety backup of current database
pg_dump --username=postgres --dbname=agrivanta \
  | gzip > /backups/agrivanta/pre-restore-$(date +%s).sql.gz

# 3. Drop and recreate database
psql --username=postgres -c "DROP DATABASE IF EXISTS agrivanta WITH (FORCE);"
psql --username=postgres -c "CREATE DATABASE agrivanta;"

# 4. Restore from backup
psql --username=postgres --dbname=agrivanta \
  --file=agrivanta-2026-11-05.sql

# 5. Verify row counts match
# (run verification queries above)

# 6. Restart application
systemctl start agrivanta

# 7. Health checks
curl http://localhost:8000/healthz  # Should return 200
curl http://localhost:8000/readyz   # Should return 200
```

---

## Test Restore Procedure (for CI/CD)

The restore procedure is validated through pytest tests that verify:
1. Database schema is intact
2. All migrations are applied
3. Core tables exist and are accessible

Run the test:
```bash
pytest backend/api/tests/test_database_backup_restore.py -v
```

---

## Production Checklist

- [ ] Backup schedule configured and running daily
- [ ] Backup files stored on separate storage (not same disk)
- [ ] Restore tested on scratch database monthly
- [ ] Row counts verified after restore
- [ ] Application passes health checks after restore
- [ ] RTO < 1 hour and RPO = 1 day target met
- [ ] Runbook kept up-to-date with actual commands

---

## Recovery Objectives

| Metric | Target |
|--------|--------|
| RPO (max acceptable data loss) | 24 hours |
| RTO (max acceptable downtime) | 1 hour |
| Backup retention | 30 days |
| Monthly restore validation | Required |
