# Report PDF export

Use `GET /api/reports/<report-name>/export?exportFormat=pdf` with the same
filters and authentication as the corresponding report. The shared layout
prints the report's existing payload, farm, selected date range, and
generation timestamp. Where the underlying report does not apply date filters
(profitability), the period is shown as "All time". The dashboard's default
uses current crop cycles; other unfiltered reports use all time.

PDF rendering uses Playwright with an installed headless Chromium-compatible
browser (Microsoft Edge, Chrome, or Chromium). On Windows it detects Edge in
its standard installation location. Elsewhere it looks for Chromium, Chrome,
or Edge on `PATH`. Set `REPORT_PDF_CHROMIUM_EXECUTABLE` to the browser's
absolute executable path to override detection. The browser and its normal
platform dependencies and fonts must be installed separately; Playwright's
browser download is not required. Chromium's sandbox must be usable by the
backend process. WeasyPrint and GTK/Pango are not required.

The renderer disables JavaScript, blocks page network requests, uses a
dedicated short-lived browser profile for each export under
`backend/.pdf-runtime/`, and removes it afterward. The backend process must be
able to create and remove files there. If Chromium cannot start or render a
PDF, the endpoint responds with HTTP 503. The `pypdf` dependency is used by
the PDF tests.

The PDF dependencies are kept separately because this feature is backend-only.
After the normal `uv sync`, install them into the project environment and
prevent subsequent commands from removing them during automatic sync:

```shell
uv sync --locked
uv pip install -r backend/requirements-pdf.txt
uv run --no-sync pytest
uv run --no-sync python backend/manage.py runserver
```

Reinstall the PDF requirements after running a regular `uv sync` or an
automatically syncing `uv run`.
