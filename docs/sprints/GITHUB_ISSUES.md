# GitHub issue drafts

Create one GitHub issue per section, then add it to **ITAMS Delivery Plan** and set the assignee, sprint, points, priority, and matching milestone. All cards below are feature-sized; use a separate feature branch, automated tests, local pytest, teammate-approved PR, and passing CI before merging.

## S1-01 — Add authentication and server-side role-based access

- **Sprint:** Sprint 1 (Oct 29–Nov 4, 2026)
- **Assignee:** @SRIRAMV570
- **Story points:** 8
- **Priority:** P0
- **Traceability:** ITAM-F-001–002, ITAM-SR-002–004; TC-AUTH-01, TC-SEC-01

**Acceptance criteria**

- [ ] Users can log in and log out; protected routes reject unauthenticated requests.
- [ ] Authorization is checked on the server for each protected operation.
- [ ] Invalid credentials and unauthorized role actions are denied without changing data.
- [ ] Passwords use a salted password hash; tests verify credentials are not logged.
- [ ] Automated positive and negative tests pass locally and in CI.

## S1-02 — Complete asset editing, reassignment, transfer, and lifecycle history

- **Sprint:** Sprint 1 (Oct 29–Nov 4, 2026)
- **Assignee:** @SharveshK1228
- **Story points:** 5
- **Priority:** P0
- **Traceability:** ITAM-F-003–008, ITAM-F-021; TC-ASSET-01–03, TC-ALLOC-01–02, TC-LIFE-01

**Acceptance criteria**

- [ ] Authorized users can edit asset details and the changes persist.
- [ ] Assets can be reassigned/transferred with previous holder and dates retained.
- [ ] Invalid state transitions and duplicate identifiers are rejected with clear feedback.
- [ ] Retirement preserves allocation/service history and removes the asset from available stock.
- [ ] Automated tests cover update, transfer, return, duplicate, and retirement behavior.

## S1-03 — Record audit events for important asset and allocation changes

- **Sprint:** Sprint 1 (Oct 29–Nov 4, 2026)
- **Assignee:** @Shreyanganesh
- **Story points:** 5
- **Priority:** P0
- **Traceability:** ITAM-F-020, ITAM-SR-005; TC-AUDIT-01

**Acceptance criteria**

- [ ] Create/edit/allocate/return/retire actions record actor, time, action, and target.
- [ ] Audit entries are immutable to ordinary users and linked to the affected record.
- [ ] Tests verify the audit event is created for successful actions and not for rejected actions.
- [ ] Sensitive credentials and license secrets never appear in audit messages.

## S1-04 — Improve dashboard summaries and keyboard-accessible form feedback

- **Sprint:** Sprint 1 (Oct 29–Nov 4, 2026)
- **Assignee:** @yashwanth00000
- **Story points:** 3
- **Priority:** P1
- **Traceability:** ITAM-F-017, ITAM-NF-005; TC-DASH-01, TC-UX-01

**Acceptance criteria**

- [ ] Dashboard counts match the seeded test data and include agreed status/category summaries.
- [ ] Key forms can be used with keyboard navigation and have visible focus.
- [ ] Validation errors are clear and associated with the relevant form field.
- [ ] Tests verify count accuracy and invalid-form feedback.

## S1-05 — Validate working increment and prepare one-minute sprint demo

- **Sprint:** Sprint 1 (Oct 29–Nov 4, 2026)
- **Assignee:** @yashwanth00000
- **Story points:** 2
- **Priority:** P1
- **Traceability:** STP entry/exit criteria; deliverables image Sprint 1 items

**Acceptance criteria**

- [ ] Run `python -m pytest -q` locally and record the result.
- [ ] Confirm the GitHub Actions PR check passes and at least one teammate approves the PR.
- [ ] Record and upload a one-minute video showing the working product.
- [ ] Record any deviations from the submitted SRS, SAD, or Test Plan.

## S2-01 — Track software licenses, entitlement compliance, and warranties

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @SharveshK1228
- **Story points:** 5
- **Priority:** P0
- **Traceability:** ITAM-F-009–011; TC-LIC-01, TC-COMP-01, TC-WAR-01

**Acceptance criteria**

- [ ] License product, entitlement, expiry, and renewal state can be recorded and retrieved.
- [ ] License usage above entitlement is flagged when usage data exists.
- [ ] Warranty provider/reference and coverage dates can be recorded and retrieved.
- [ ] Inputs are validated and sensitive license data is not exposed in logs.
- [ ] Tests cover license, over-entitlement, and warranty cases.

## S2-02 — Schedule maintenance and preserve service history

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @yashwanth00000
- **Story points:** 5
- **Priority:** P0
- **Traceability:** ITAM-F-012–013; TC-MAINT-01–02

**Acceptance criteria**

- [ ] Maintenance can be scheduled with due date, priority, status, and responsible team/technician.
- [ ] Completed service events are linked to an asset with date and notes.
- [ ] Maintenance list shows due/overdue state accurately.
- [ ] Tests cover schedule creation, completion, and retained service history.

## S2-03 — Generate, assign, and resolve expiry and maintenance alerts

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @Shreyanganesh
- **Story points:** 5
- **Priority:** P1
- **Traceability:** ITAM-F-014–016; TC-ALERT-01–03

**Acceptance criteria**

- [ ] Configured thresholds generate alerts for license/warranty expiry, overdue maintenance, and incomplete records.
- [ ] Re-running alert generation does not create duplicate active alerts.
- [ ] Authorized users can acknowledge, assign, and resolve alerts.
- [ ] Alert state changes retain actor and timestamp history.
- [ ] Tests cover threshold boundaries, duplicate prevention, and status history.

## S2-04 — Add reports, CSV export, and validated CSV import

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @SRIRAMV570
- **Story points:** 8
- **Priority:** P1
- **Traceability:** ITAM-F-018–019, ITAM-F-022; TC-REPORT-01–02, TC-IMPORT-01

**Acceptance criteria**

- [ ] Inventory/status report data and totals match database records and requested filters.
- [ ] CSV export contains only authorized, selected report data and opens successfully.
- [ ] CSV import validates the agreed template and reports row-specific errors.
- [ ] Invalid rows do not silently corrupt or discard valid imported records.
- [ ] Tests cover report accuracy, export content, and mixed valid/invalid CSV input.

## S2-05 — Run security, performance, compatibility, and backup/restore checks

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @SharveshK1228
- **Story points:** 3
- **Priority:** P0
- **Traceability:** ITAM-NF-001, 003, 005–007; ITAM-SR-001–006; TC-SEC-02–06, TC-PERF-01, TC-UX-01, TC-REC-01

**Acceptance criteria**

- [ ] Security tests cover malformed/injection-like input, role denial, and secret/log handling.
- [ ] Performance is measured against the SRS dataset target where the test environment permits.
- [ ] Keyboard/browser usability checks and a SQLite backup/restore exercise are documented.
- [ ] Record actual results and explicitly defer any unsupported production-only measurements.
- [ ] No unresolved critical security or data-loss issue remains at sprint exit.

## S2-06 — Finish RTM and setup guide, record two-minute demo, freeze release

- **Sprint:** Sprint 2 (Nov 5–11, 2026)
- **Assignee:** @yashwanth00000
- **Story points:** 2
- **Priority:** P1
- **Traceability:** STP exit criteria; deliverables image Sprint 2 items

**Acceptance criteria**

- [ ] RTM links each implemented requirement to its automated/manual test and actual status.
- [ ] Setup, configuration, backup/restore, and known limitations are documented.
- [ ] Upload a two-minute video demonstrating the working product with synthetic data.
- [ ] Tag/freeze the demo version and document any remaining deferred requirements.
