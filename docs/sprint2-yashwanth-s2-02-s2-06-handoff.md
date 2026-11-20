# Sprint 2 Handoff — Yashwanth (S2-02 and S2-06)

**Owner:** @yashwanth00000  
**Sprint:** November 5–11, 2026  
**Handoff refresh:** November 20, 2026  
**Feature branch:** \`feature/yashwanth-s2-maintenance-demo\`  
**Scope:** S2-02 (5 points) and S2-06 (2 points)

## Delivery status

| Backlog item | Evidence in this change | Status |
|---|---|---|
| S2-02 — Schedule maintenance and preserve service history | \`maintenance.py\`, three maintenance templates, dashboard entry point, and \`tests/test_maintenance.py\` | Implemented on this branch; CI result is recorded in the PR after the run completes |
| S2-06 — RTM, setup guide, demo and release freeze | This handoff, traceability table, setup/backup instructions and two-minute demo run sheet | Documentation prepared; live video recording and final release tag remain pending |

## S2-02 implementation

### Data model

- \`maintenance_schedules\` stores the asset, work title, due date, priority, responsible team/technician, status, notes, creator and timestamps.
- \`maintenance_service_history\` stores the linked asset, completed schedule, service date, technician/provider, notes and creator.
- A unique constraint permits one completion record per schedule. Database triggers prevent service-history UPDATE and DELETE operations.
- Indexes support due-date/status queries and asset-specific schedule/history retrieval.

### Workflows

- \`GET /maintenance\` lists schedules and service history. Due state is calculated from the due date as Upcoming, Due today, Overdue or Completed.
- \`GET/POST /maintenance/new\` lets an administrator or asset manager schedule work for a non-retired asset.
- \`POST /maintenance/<id>/start\` moves a Scheduled item to In progress.
- \`GET/POST /maintenance/<id>/complete\` validates the service date, technician/provider and notes, completes the schedule, inserts one service-history event and appends an audit event in the same transaction.
- All write routes use the application's existing role decorator and CSRF protection. Read-only roles may view the list but cannot schedule, start or complete work.

### Acceptance-to-test traceability

| Requirement / test | Implementation | Automated evidence |
|---|---|---|
| ITAM-F-012 — Schedule maintenance with due date, priority, status and responsible party | Schedule form and \`maintenance_schedules\` | \`test_maintenance_schedule_is_created_and_visible\` |
| ITAM-F-012 — Reject invalid dates and retired-asset schedules | Server-side validation | \`test_invalid_due_date_and_retired_asset_are_rejected\` |
| ITAM-F-012 — Identify overdue schedules | Due-state SQL expression based on SQLite's current date | \`test_overdue_maintenance_is_identified_from_due_date\` |
| ITAM-F-013 — Retain completed service date and notes against an asset | Completion workflow and \`maintenance_service_history\` | \`test_start_and_complete_preserve_service_history\` |
| ITAM-F-013 — Reject invalid completion data without changing status | Completion validation before transaction | \`test_invalid_service_record_does_not_complete_schedule\` |
| ITAM-F-012/013 — Enforce manager write access | Existing server-side RBAC policy | \`test_read_only_employee_can_view_but_cannot_manage_maintenance\` |
| ITAM-F-013 — Preserve service records after completion | SQLite no-UPDATE/no-DELETE triggers | \`test_service_history_rows_are_immutable\` |

Run the full suite with \`python -m pytest -q\`. CI is authoritative for the pushed commit; do not record a local result unless the command has actually been run locally. The release commit `fd77b3a04168468508fc01c24bae7e032ae88f70` passed the GitHub Actions `Tests` workflow on 2026-11-20. See [the successful run](https://github.com/SRIRAMV570/IT-Infrastructure-Asset-Management-System/actions/runs/44704168833).

## S2-06 — Setup and operations guide

### Prerequisites

- Python 3.12 or newer.
- Windows PowerShell, macOS Terminal or a Linux shell.
- A clean checkout of the repository.

### Windows PowerShell setup

\`\`\`powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt

# Generate a development signing key for this shell session.
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")

# Create the first administrator; the CLI prompts for a password.
flask --app app:create_app create-admin --username admin

# Start the local development server.
python app.py
\`\`\`

Open \`http://127.0.0.1:5000\` and sign in with the administrator credentials created above. The application creates \`instance/itams.sqlite3\` automatically. Never commit the database, signing key or real credentials.

For a deployed HTTPS environment, set a stable secret through the hosting environment and set \`SESSION_COOKIE_SECURE=1\`. Do not set the secure-cookie flag for plain local HTTP, or the browser will not send the session cookie.

### Test and demo preparation

\`\`\`powershell
python -m pytest -q
\`\`\`

Use only synthetic assets, users and service notes for the demo. The CI workflow runs the same pytest command on pushes and pull requests.

### SQLite backup and restore

Stop the application before copying or replacing its live database. Create the backup directory first:

\`\`\`powershell
New-Item -ItemType Directory -Force backups
\`\`\`

The S2-05 work in PR #9 adds a standard-library SQLite online-backup utility. After that PR is merged into \`main\`, use:

\`\`\`powershell
python scripts/sqlite_backup.py backup instance/itams.sqlite3 backups/itams-backup.sqlite3
python scripts/sqlite_backup.py verify backups/itams-backup.sqlite3
python scripts/sqlite_backup.py restore backups/itams-backup.sqlite3 instance/itams-restore-test.sqlite3
python scripts/sqlite_backup.py verify instance/itams-restore-test.sqlite3
\`\`\`

If the helper script is unavailable in a particular checkout, a portable Python standard-library backup can be made without it:

\`\`\`powershell
python -c "import sqlite3; src=sqlite3.connect('instance/itams.sqlite3'); dst=sqlite3.connect('backups/itams-backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
python -c "import sqlite3; db=sqlite3.connect('backups/itams-backup.sqlite3'); print(db.execute('PRAGMA quick_check').fetchone()[0]); db.close()"
\`\`\`

To test restore safely, restore to a new, empty path rather than overwriting the live database:

\`\`\`powershell
python -c "import sqlite3; src=sqlite3.connect('backups/itams-backup.sqlite3'); dst=sqlite3.connect('instance/itams-restore-test.sqlite3'); src.backup(dst); dst.close(); src.close()"
python -c "import sqlite3; db=sqlite3.connect('instance/itams-restore-test.sqlite3'); print(db.execute('PRAGMA quick_check').fetchone()[0]); db.close()"
\`\`\`

Both integrity checks should print \`ok\`. Keep backups outside version control and test a restored copy before using it. A test-database round trip is not a production disaster-recovery certification.

## Two-minute demo run sheet

| Time | Demonstration |
|---|---|
| 0:00–0:20 | Sign in as the seeded administrator and show the ITAMS dashboard. |
| 0:20–0:40 | Open Assets and show a synthetic laptop or server asset. |
| 0:40–1:00 | Open Maintenance and schedule an inspection with a due date, priority and responsible team. |
| 1:00–1:20 | Show the schedule list, asset link and due-state label. Use a past due date in the demo dataset to demonstrate Overdue. |
| 1:20–1:45 | Start the work, record the service date, technician and notes, then complete the schedule. |
| 1:45–2:00 | Show the linked service-history entry and explain that completed service events cannot be edited or deleted through normal SQL operations. |

**Recording status (optional):** The run sheet is provided as a suggested walkthrough. No screen recording is claimed to have been captured or uploaded. Recording is optional unless faculty or the course submission instructions explicitly require a video. If requested, record the running application with synthetic data; do not include real credentials or personal data.

## Sprint 2 release traceability snapshot

This table reflects the repository state verified on November 20, 2026. The listed feature and handoff pull requests are merged into `main`.

| Sprint item | Owner | Evidence | Release status |
|---|---|---|---|
| S2-01 — License and warranty records | Sharvesh | PR #9; `license_warranty.py` and related tests | Merged into `main` |
| S2-02 — Maintenance and service history | Yashwanth | PRs #10, #13, #14; `maintenance.py`, templates and tests | Merged into `main`; dashboard completion counter follow-up in PR #15 |
| S2-03 — Expiry and maintenance alerts | Shreyanganesh | PR #11; `alerts.py`, alert templates and tests | Merged into `main` |
| S2-04 — Reports and CSV import/export | SRI RAM V | PR #12; reports and validated CSV import/export | Merged into `main` |
| S2-05 — Security, performance and recovery checks | Sharvesh | PR #9; security/quality tests and SQLite backup/restore utility | Merged into `main`; manual compatibility and representative-environment restore checks should still be completed if required |
| S2-06 — RTM, setup guide, demo and release freeze | Yashwanth | PRs #10 and #13; this handoff | Documentation integrated; `v1.0.0` published. Recording is optional unless requested by faculty |

## Release freeze and post-release checklist

- [x] Integrate the assigned Sprint 2 feature PRs into `main` after review and CI.
- [x] Add maintenance regression tests, dashboard maintenance completion-count coverage and traceability.
- [x] Document setup, secret configuration, database location, and safe backup/restore steps.
- [x] Prepare the optional two-minute demo run sheet.
- [x] Publish the immutable `v1.0.0` release tag on commit `fd77b3a04168468508fc01c24bae7e032ae88f70`.
- [x] Verify the GitHub Actions Tests workflow passed for the release commit.
- [ ] Complete a manual browser-based end-to-end walkthrough and record its outcome. A video recording is optional unless faculty explicitly requires it.
- [ ] Confirm `main` branch protection in repository Settings. The GitHub integration used for this documentation update could not read the branch-protection endpoint, so no protection status is claimed here.
- [ ] If documentation corrections are approved, merge them as a post-release follow-up commit/PR. Do not move, delete, or recreate `v1.0.0`.

**Release decision:** `v1.0.0` is the fixed faculty-submission snapshot. Its tag must remain unchanged. The README and this handoff are being corrected on a separate documentation branch after the release; merging those corrections will advance `main` but will not alter the tagged submission commit. Manual browser verification and branch-protection confirmation remain separate sign-off checks. The actual demo video is optional unless faculty or the course instructions require it.
