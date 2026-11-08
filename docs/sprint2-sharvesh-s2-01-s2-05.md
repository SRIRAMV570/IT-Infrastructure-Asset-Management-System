# S2-05 Quality and recovery checks

## Automated security coverage
The S2 regression suite checks server-side role denial, CSRF rejection, parameterized handling of injection-like input, validation boundaries, and that activation keys/passwords are not represented in the license schema or audit payload. The license form accepts a non-secret procurement reference only; never store activation keys, credentials, or tokens in this application.

Run the full suite with:

    python -m pytest -q

## SQLite backup and restore
Use a consistent SQLite online backup (not a raw copy of a live database):

    python scripts/sqlite_backup.py backup instance/itams.sqlite3 backups/itams-YYYYMMDD.sqlite3
    python scripts/sqlite_backup.py verify backups/itams-YYYYMMDD.sqlite3
    python scripts/sqlite_backup.py restore backups/itams-YYYYMMDD.sqlite3 instance/itams-restore-test.sqlite3
    python scripts/sqlite_backup.py verify instance/itams-restore-test.sqlite3

Restore refuses to overwrite an existing destination. Keep backup files outside version control and protect them as confidential data. This utility verifies SQLite integrity; it does not claim a full disaster-recovery or production restore drill.

## Performance and compatibility
Run the inventory smoke benchmark:

    python scripts/performance_smoke.py

It creates a temporary database with synthetic records and measures parameterized inventory filtering. This is a repeatable smoke measurement, not a formal SRS performance acceptance result; the SRS dataset/latency target must be confirmed against the submitted specification and tested on the agreed environment.

Manual browser/keyboard compatibility checklist:
- Chrome/Edge and Firefox: sign in, navigate with keyboard only, create/edit a license and warranty, inspect validation feedback and tables.
- Mobile viewport: confirm navigation, forms, and horizontally scrollable tables remain usable.
- Verify visible focus, label association, zoom to 200%, and no horizontal page overflow.
- Record browser/version, OS, viewport, tester, date, defects, and retest outcome in the sprint handoff.
