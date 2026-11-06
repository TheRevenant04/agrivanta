# Planned activity resources

The following collections are nested under `/api/activities/{activityId}`:

| Collection | Request fields |
| --- | --- |
| `planned-inputs` | `itemId`, `quantity` |
| `planned-labour` | `hours` |
| `planned-equipment` | `equipmentId`, `hours` |

Collections support GET and POST; append `/{lineId}` for GET, PUT, PATCH,
or DELETE. Responses identify the line and activity with `id` and `activityId`.
Quantities and hours must be positive, with at most ten integer and four
fractional digits. Inputs and equipment must belong to the activity's farm;
each can occur at most once per activity. Labour lines may repeat.

Activity visibility governs reads; owners and managers can change plans for
open cycles. These records are independent of stock movements, labour records,
and equipment usage. The existing aggregate `resource-needs` endpoint remains
separate for compatibility and does not synchronize with these collections.
