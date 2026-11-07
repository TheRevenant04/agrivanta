# Report PDF export

Use `GET /api/reports/<report-name>/export?exportFormat=pdf` with the same
filters and authentication as the corresponding report. The shared layout
prints the report's existing payload, farm, selected date range, and
generation timestamp. Where the underlying report does not apply date filters
(profitability), the period is shown as "All time". The dashboard's default
uses current crop cycles; other unfiltered reports use all time.

PDF rendering uses WeasyPrint, which requires native Pango, GLib, HarfBuzz,
Fontconfig and installed fonts in addition to the Python packages in
`backend/requirements-pdf.txt`. On Windows, install a GTK/Pango runtime and
put its DLL directory in `WEASYPRINT_DLL_DIRECTORIES`; on Linux, install the
corresponding distribution packages. Follow the platform-specific
[WeasyPrint installation guide](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation).
The `pypdf` dependency is used by the PDF tests.

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
