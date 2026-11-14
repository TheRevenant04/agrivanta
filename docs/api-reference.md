# API Reference

Agrivanta provides a RESTful API with OpenAPI 3.0 specification. The API is farm-scoped — all resources belong to the authenticated user's farm.

## Base URL

| Environment | URL |
|-------------|-----|
| Local Development | `http://localhost:8000/api/` |
| Production | `https://api.yourdomain.com/api/` |

## Authentication

**JWT Token Authentication** (Bearer token in Authorization header):

```http
Authorization: Bearer <access_token>
```

**Endpoints:**
- `POST /api/auth/login/` — Obtain access/refresh tokens
- `POST /api/auth/refresh/` — Refresh access token
- `POST /api/auth/register/` — Register new user (farm owner)
- `POST /api/auth/password/reset/` — Request password reset
- `POST /api/auth/password/reset/confirm/` — Confirm password reset

**Token Lifetimes:**
- Access token: 15 minutes
- Refresh token: 7 days

## Core Resources

### Farm & Fields
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/farm/` | GET, PUT | Get/update farm configuration |
| `/api/fields/` | GET, POST, PUT, DELETE | Manage fields |
| `/api/fields/{id}/` | GET, PUT, DELETE | Single field operations |

### Crops & Varieties
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/crops/` | GET, POST | List/create crops |
| `/api/crops/{id}/` | GET, PUT, DELETE | Single crop |
| `/api/varieties/` | GET, POST | List/create varieties |
| `/api/varieties/{id}/` | GET, PUT, DELETE | Single variety |

### Units & Conversions
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/units/` | GET, POST | Measurement units |
| `/api/units/{id}/` | GET, PUT, DELETE | Single unit |
| `/api/conversions/` | GET, POST | Unit conversions |
| `/api/conversions/{id}/` | GET, PUT, DELETE | Single conversion |

### Crop Cycles
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/crop-cycles/` | GET, POST | List/create crop cycles |
| `/api/crop-cycles/{id}/` | GET, PUT, DELETE | Single crop cycle |
| `/api/crop-cycles/{id}/close/` | POST | Close crop cycle (locks records) |
| `/api/crop-cycles/{id}/reopen/` | POST | Reopen closed cycle (authorized only) |

### Activity Planning
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/activity-types/` | GET, POST | Activity templates |
| `/api/activity-types/{id}/` | GET, PUT, DELETE | Single template |
| `/api/activities/` | GET, POST | Planned activities |
| `/api/activities/{id}/` | GET, PUT, DELETE | Single activity |
| `/api/activities/{id}/complete/` | POST | Mark activity complete |

### Inventory
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/inventory/` | GET, POST | Inventory items |
| `/api/inventory/{id}/` | GET, PUT, DELETE | Single item |
| `/api/stock-movements/` | GET, POST | Stock movements (purchase, usage, adjustment) |
| `/api/stock-movements/{id}/` | GET, PUT, DELETE | Single movement |
| `/api/low-stock-alerts/` | GET | Items below threshold |

### Financials
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/expenses/` | GET, POST | Expenses and purchases |
| `/api/expenses/{id}/` | GET, PUT, DELETE | Single expense |
| `/api/payments/` | GET, POST | Payments received/made |
| `/api/payments/{id}/` | GET, PUT, DELETE | Single payment |
| `/api/budgets/` | GET, POST | Crop-cycle and category budgets |
| `/api/budgets/{id}/` | GET, PUT, DELETE | Single budget |
| `/api/suppliers/` | GET, POST | Supplier profiles |
| `/api/customers/` | GET, POST | Customer profiles |

### Harvests & Sales
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/harvests/` | GET, POST | Harvest records |
| `/api/harvests/{id}/` | GET, PUT, DELETE | Single harvest |
| `/api/sales/` | GET, POST | Sales records |
| `/api/sales/{id}/` | GET, PUT, DELETE | Single sale |

### Reporting
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/dashboard/kpis/` | GET | Dashboard KPIs (with trend data) |
| `/api/reports/operations/` | GET | Operational report |
| `/api/reports/inventory/` | GET | Inventory report |
| `/api/reports/financial/` | GET | Financial report |
| `/api/reports/profitability/` | GET | Profitability by field/crop-cycle/season |
| `/api/reports/yield-comparison/` | GET | Cross-field yield comparison |
| `/api/reports/break-even/` | GET | Break-even analysis |
| `/api/reports/exports/` | POST | Generate export (PDF/Excel/CSV) |

### Notifications
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/notifications/` | GET | List notifications |
| `/api/notifications/{id}/read/` | POST | Mark as read |
| `/api/notifications/mark-all-read/` | POST | Mark all as read |

### AI Chat
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/chat/` | POST (streaming) | Natural-language queries with evidence |

**Request:**
```json
{
  "question": "What was my corn profitability last season?",
  "context": {
    "crop_cycle_id": "optional-uuid",
    "reporting_period": "optional"
  }
}
```

**Response:** NDJSON stream with events:
- `type: "tool_call"` — Function invoked
- `type: "tool_result"` — Function result with data
- `type: "answer_chunk"` — Streaming answer text
- `type: "citations"` — Evidence references
- `type: "done"` — Completion

### Imports
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/imports/preview/` | POST | Preview CSV/Excel import |
| `/api/imports/commit/` | POST | Confirm and execute import |
| `/api/imports/templates/` | GET | Download import templates |

### Attachments
| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/attachments/` | GET, POST | Upload/list attachments |
| `/api/attachments/{id}/` | GET, DELETE | Single attachment |

## Query Parameters

### Pagination
```
?page=1&page_size=25
```
Response includes `count`, `next`, `previous`, `results`.

### Filtering
Most list endpoints support Django-filter syntax:
```
?crop=corn&status=completed&date_after=2026-01-01
```

### Ordering
```
?ordering=-date_created,field_name
```

### Reporting Periods
```
?period=2026-q1          # Calendar quarter
?season=2026-main        # Agricultural season
?date_from=2026-01-01&date_to=2026-12-31
```

## Error Responses

**400 Bad Request:**
```json
{
  "detail": "Validation failed",
  "errors": {
    "field_name": ["Error message"]
  }
}
```

**401 Unauthorized:**
```json
{
  "detail": "Authentication credentials were not provided."
}
```

**403 Forbidden:**
```json
{
  "detail": "You do not have permission to perform this action."
}
```

**404 Not Found:**
```json
{
  "detail": "Not found."
}
```

**409 Conflict** (e.g., editing posted transaction):
```json
{
  "detail": "Posted transactions cannot be modified. Create a reversal instead.",
  "code": "TRANSACTION_LOCKED"
}
```

**500 Server Error:**
```json
{
  "detail": "An unexpected error occurred.",
  "request_id": "uuid-for-support"
}
```

## Rate Limiting

- Anonymous: 100 requests/hour
- Authenticated: 1000 requests/hour
- AI Chat: 20 requests/minute

Headers included in responses:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

## OpenAPI Specification

The full OpenAPI 3.0 spec is available at:
- **Development**: `http://localhost:8000/openapi.yaml`
- **Repository**: `backend/api/openapi.yaml`

Generate TypeScript client:
```bash
cd frontend
npm run api:generate
```

## Versioning

API versioning via URL path: `/api/v1/` (current).
Breaking changes will increment version; v1 maintained for 12 months after v2 release.