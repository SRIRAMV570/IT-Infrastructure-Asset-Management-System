# Sprint 2 Handoff — S2-03 Alerts

**Owner:** @Shreyanganesh  
**Backlog item:** S2-03 — Generate, assign, and resolve expiry and maintenance alerts  
**Estimate:** 5 story points  
**Traceability:** ITAM-F-014–016; TC-ALERT-01–03  
**Feature branch:** `feature/shreyan-sprint2`

## Delivered scope

- Generate alerts for software license expiry, warranty expiry, overdue maintenance, and incomplete non-retired asset records.
- Use configurable lead/overdue thresholds and severity levels.
- Prevent duplicate active alerts when generation is repeated.
- Provide authenticated list and detail screens.
- Allow administrators and asset managers to acknowledge, assign/reassign, and resolve alerts.
- Retain an immutable actor/timestamp history for generated and changed alerts.
- Add an operational Flask CLI command so alert generation can be scheduled externally.

This implementation is limited to S2-03. It does not implement license/warranty CRUD (S2-01), maintenance scheduling/service history (S2-02), or reporting/import/export (S2-04).

## Rule inputs and default thresholds

| Alert condition | Source table | Default rule | Default severity |
|---|---|---|---|
| License expiry | `software_licenses` | Expiry date is within 30 days, including the expiry date and already-expired records | Medium; High at 7 days or fewer; Critical after expiry |
| Warranty expiry | `warranties` | Coverage end date is within 30 days; future coverage that has not started is ignored | Medium; High at 7 days or fewer; Critical after expiry |
| Maintenance overdue | `maintenance_schedules` | A non-completed schedule is at least 1 day overdue | Medium; High at 7 days; Critical at 30 days |
| Incomplete asset | `assets` | Any configured completeness field is blank on a non-retired asset | Medium |

The defaults can be overridden through Flask application configuration:

- `ALERT_LICENSE_EXPIRY_DAYS` (default `30`)
- `ALERT_WARRANTY_EXPIRY_DAYS` (default `30`)
- `ALERT_MAINTENANCE_OVERDUE_DAYS` (default `1`)
- `ALERT_MAINTENANCE_HIGH_DAYS` (default `7`)
- `ALERT_MAINTENANCE_CRITICAL_DAYS` (default `30`)
- `ALERT_INCOMPLETE_ASSET_FIELDS` (default: `manufacturer`, `model`, `serial_number`, `location`, `purchase_date`)

The incomplete-field list is restricted to known asset columns; untrusted input is not used as a SQL identifier. Fields can be omitted from the policy by changing this configuration.

## Dependency and integration boundary

S2-03 consumes the schemas owned by S2-01 and S2-02:

- `software_licenses` and `warranties` from Sharvesh's S2-01 implementation.
- `maintenance_schedules` from Yashwanth's S2-02 implementation.

At the time this branch was prepared, PR #9 (S2-01/S2-05) and PR #10 (S2-02/S2-06) were open and those source tables were not part of `main`. The generator therefore checks for each source table and skips only that source when it is unavailable. The Alerts screen reports the missing integration tables. No teammate-owned source module or schema is copied or modified here. After those PRs merge, alert generation will read their existing tables using the agreed column names.

## Persistence and state history

- `alerts` stores the source reference, alert type, due date, severity, status, assignment and resolution notes.
- A partial unique index prevents more than one active alert for the same `dedupe_key`. Re-running generation refreshes an existing active alert instead of creating another. A resolved condition may create a new active alert on a later run if the source condition remains.
- `alert_history` stores event type, actor ID/username, old/new status, old/new assignee, notes and database timestamp.
- SQLite triggers reject UPDATE and DELETE operations on alert-history rows.
- State transitions and global audit events are written in the same transaction.
- Generation invoked from the UI records the signed-in manager. CLI generation records the actor as `system`.

## Routes and operations

| Method | Route / command | Access | Purpose |
|---|---|---|---|
| GET | `/alerts` | Authenticated | List/filter alerts and view status counts |
| GET | `/alerts/<id>` | Authenticated | View an alert and its history |
| POST | `/alerts/generate` | Admin / asset manager | Generate alerts from available source tables |
| POST | `/alerts/<id>/acknowledge` | Admin / asset manager | Acknowledge an open or assigned alert |
| POST | `/alerts/<id>/assign` | Admin / asset manager | Assign/reassign to a non-auditor account |
| POST | `/alerts/<id>/resolve` | Admin / asset manager | Resolve and retain resolution notes |
| CLI | `flask --app app:create_app generate-alerts` | Operator | Run the same generation rules from a scheduler |

The CLI accepts `--as-of YYYY-MM-DD` for repeatable threshold tests and controlled demonstrations. For production-style periodic generation, schedule the CLI command using the host's scheduler; no background scheduler or email notification service is introduced by S2-03.

All state-changing routes use the application's existing session authentication, server-side role checks and CSRF enforcement.

## Test coverage

`tests/test_alerts.py` covers:

- License and warranty expiry threshold boundaries.
- Overdue-maintenance and incomplete-asset rules.
- Repeated generation and active-alert duplicate prevention.
- Acknowledge, assign, resolve and actor/timestamp history.
- Global audit-event integration.
- Role denial and CSRF enforcement.
- Graceful operation while S2-01/S2-02 source tables are not yet merged.
- Alert-history immutability.
- CLI generation and the system actor.

Run the full suite from the repository root:

```bash
python -m pytest -q
```

Record actual local and CI results in the PR after executing them. No local test result is claimed in this handoff.

## Demonstration run sheet

1. Sign in as an administrator or asset manager and open **Alerts**.
2. With S2-01/S2-02 merged, add synthetic source records: a license expiring within 30 days, a warranty expiring within 30 days, and a maintenance schedule due yesterday.
3. Leave one optional asset completeness field blank on a non-retired asset.
4. Select **Generate alerts** and show the new alerts with their source, severity, due date and status.
5. Select **Generate alerts** again and show that the active alert count does not increase.
6. Open an alert, acknowledge it, assign it to a non-auditor test account, and resolve it with a short note.
7. Show the history rows with actor, event, old/new status, assignment and timestamp.

## Limitations

- Alerts are in-app records only; no email, SMS or push notifications are sent.
- Periodic execution must be configured by the operator using the CLI.
- Source-driven alerts for licenses, warranties and maintenance require the S2-01 and S2-02 modules to be integrated.
- The default incomplete-record policy is configurable and should be confirmed against the final approved SRS data-completeness rules.
- The workflow does not silently auto-resolve alerts when their source condition changes; an authorized manager resolves them, preserving the operational decision in history.
