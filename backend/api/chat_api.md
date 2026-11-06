# Farm chat streaming API

`POST /api/chat` requires the same authenticated DRF credentials as other farm
APIs. Its JSON request body is `{"question":"..."}`. Questions must be
non-empty and no longer than 4,000 characters.

The endpoint responds as `application/x-ndjson`. Each line is a JSON event:

- `{"type":"token","text":"..."}` carries the next answer text fragment.
- `{"type":"final","answer":"...","evidence":{...}}` ends a successful or
  deterministic limitation response. `answer` is the concatenation of the
  preceding token text. `evidence` contains:
  - `figures`: exact numeric values returned by query tools, with the tool
    name and a JSON Pointer into its `/data` result.
  - `reportingPeriods` and `cropCycles`: deduplicated metadata from tool
    evidence.
  - `calculationBasis`: the query tool responsible for each figure set and
    `recomputedByChat` (always `false`).
  - `toolResults`: the arguments and complete structured result from each
    read-only query tool.
- `{"type":"error","error":{"code":"llm_stream_error","message":"..."}}`
  indicates that generation failed after streaming began; no final event is
  emitted.

When a permitted query reports missing or unusable data, the endpoint skips
LLM answer generation and streams an explicit limitation, followed by a final
event whose evidence contains the tool errors and any exact figures available
from successful queries. It never estimates missing values. Chat orchestration
only invokes the registered read-only query functions and does not write farm
records.
