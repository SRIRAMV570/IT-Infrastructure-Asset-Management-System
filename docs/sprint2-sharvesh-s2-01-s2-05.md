# Sprint 2 Handoff — S2-01 and S2-05

**Owner:** @SharveshK1228  
**Sprint:** Sprint 2 (November 5–11, 2026)  
**Feature branch:** feature/sharvesh-s2-license-warranty  
**Pull request:** #9

## S2-01 — License, entitlement and warranty management

### Implemented
- Added a software-license table with optional asset association, product/vendor, non-secret procurement reference, entitlement count, current usage, expiry date, renewal state and notes.
- Added create, list and edit screens for license records.
- Added a computed over-entitlement flag when current usage exceeds entitlement.
- Added asset-linked warranty records with provider/reference, coverage start/end dates and notes.
- Added create, list and edit screens for warranties; warranty information is visible from the linked asset detail page.
- Restricted create/edit operations to admin and asset_manager roles. Read-only roles can view records.
- Reused the application's login, server-side RBAC and CSRF controls.
- Added license/warranty audit events. Audit details exclude the license reference; the application does not store activation keys, passwords or tokens.

### Automated acceptance evidence
- License create/list/edit and entitlement-overuse boundary.
- Invalid quantities, dates, renewal states, and asset associations.
- Warranty asset linkage, list/detail visibility, and reversed/invalid coverage dates.
- Role denial, CSRF denial, injection-like text handling, and sensitive-field minimization.

## S2-05 — Security, performance and recovery

### Automated results — GitHub Actions
**Run:** https://github.com/SRIRAMV570/IT-Infrastructure-Asset-Management-System/actions/runs/42501436781  
**Commit:** 4345a1a46a48bdbd7670a6525725a15e3a2ce7be  
**Result:** PASS — latest run on 6ad861670b084a614c81a2db4d36dfdac2b59049: 51 tests passed in 11.71 seconds.

### Performance smoke measurement
- Synthetic rows: 5,000.
- Matching rows: 1,667.
- Indexed category/status query: 0.153 ms in the recorded GitHub-hosted runner.
- Query plan: SEARCH assets USING INDEX idx_assets_category_status (category=? AND status=?).

This is a small synthetic SQLite smoke measurement, not a formal performance acceptance result. It must not be compared to an SRS latency requirement until the required dataset size, workload and threshold are confirmed from the submitted SRS and reproduced in the agreed environment.

### Backup and restore
- Automated test created a consistent SQLite online backup, ran PRAGMA quick_check, restored to a new database path, and verified integrity and the administrator row.
- The restore utility refuses to overwrite an existing destination.
- This proves a test-database round trip, not production disaster-recovery readiness.

### Manual checks still required
- [ ] Keyboard-only browser checks and visible focus.
- [ ] Chrome/Edge and Firefox functional checks.
- [ ] Mobile viewport and 200% zoom checks.
- [ ] Record OS, browser versions, tester, date, screenshots and defects.
- [ ] Run backup/restore using a representative non-production project database and verify the restored application starts.
- [ ] Confirm the SRS performance target and run its agreed workload.

## Limitations / integration boundaries
- Expiry and renewal dates are stored and displayed. The existing S2-03 alert module on `main` remains registered alongside this module and consumes the license and warranty tables.
- License usage is a manually recorded count. No endpoint or telemetry integration is claimed to discover real-time usage.
- Activation keys and other credentials are deliberately not stored.
- Manual browser compatibility and production-scale performance sign-off remain pending.

## Reproduction
    python -m pytest -q
    python scripts/performance_smoke.py
    python scripts/sqlite_backup.py backup instance/itams.sqlite3 backups/itams-test.sqlite3
    python scripts/sqlite_backup.py verify backups/itams-test.sqlite3
    python scripts/sqlite_backup.py restore backups/itams-test.sqlite3 instance/itams-restore-test.sqlite3
    python scripts/sqlite_backup.py verify instance/itams-restore-test.sqlite3
