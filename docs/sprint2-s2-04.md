# Sprint 2 — S2-04: Reports, CSV export and validated CSV import

Owner: SRI RAM V (@SRIRAMV570)

## Delivered in this branch

- Reports page with inventory totals grouped by asset status and category.
- CSV export at `GET /reports/assets.csv`, including asset metadata, active assignee and creation timestamp. Optional `status` filtering is supported.
- CSV import at `POST /reports/import`, restricted to `admin` and `asset_manager`.
- UTF-8 / UTF-8-BOM input, strict documented header order, required-field and status validation, ISO date validation, duplicate tag/serial checks, 1 MiB file limit and 500-row limit.
- Atomic import: any invalid row rejects the entire file; successful inserts and audit events commit together.
- Allocated imports require an assignee and create the corresponding active allocation row. Non-allocated rows cannot specify an assignee.
- Import uses the application's existing authentication, role and CSRF policies.

## CSV template

```csv
asset_tag,name,category,manufacturer,model,serial_number,status,location,purchase_date,assignee
LAP-CSV-01,Developer laptop,Laptop,Acme,Book,CSV-001,available,Room 1,2026-10-01,
```

Allowed statuses: `available`, `allocated`, `maintenance`, `retired`.

For `allocated` rows, `assignee` is required. For other statuses, it must be blank. Asset tags are required; serial numbers may be blank. Dates must use `YYYY-MM-DD`.

## Validation evidence

Automated regression tests are included in `tests/test_sprint2_reports.py` for report rendering, CSV download headers, successful import, allocation and audit creation, atomic rejection, duplicate prevention, allocated-assignee validation, CSRF enforcement and role restrictions.

Run locally from the repository root:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

Do not mark the story accepted until the required GitHub Actions check passes and a reviewer verifies the implementation against the acceptance criteria.
