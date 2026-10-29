# ITAMS — Updated Test Case Document (Part 3)

**Prepared:** 29 October 2026 | **Evidence baseline:** Sprint 1, S1-01 authentication/RBAC integrated, S1-02 lifecycle changes under PR #5.

**Purpose.** Update the test case inventory to match implemented Sprint-1 behavior, specify expected results, and distinguish automated checks from not-yet-implemented features. The [project Test Plan](../ITAMS_Test_Plan.pdf) remains the governing test strategy. Actual results appear in the generated Part-3 reports, not in this planning document.

## Updated executable test cases

| Case ID | Requirement / scenario | Expected result | Test implementation |
|---|---|---|---|
| TC-AUTH-01 | Valid admin login and protected routes | Authenticated access; anonymous redirect to login | `test_login_uses_salted_password_hash`, `test_protected_pages_redirect_anonymous_users_to_login` |
| TC-AUTH-02 | Incorrect login | Generic rejection and no authenticated session | `test_invalid_login_is_generic_and_does_not_authenticate` |
| TC-AUTH-03 | Read-only roles attempt mutation | HTTP 403 and no asset mutation | `test_employee_can_read_but_cannot_create_or_allocate_assets`, `test_read_only_roles_cannot_register_assets` |
| TC-AUTH-04 | Invalid / missing CSRF token | HTTP 400, mutation blocked | `test_mutating_requests_require_a_valid_csrf_token`, `test_tc_12_invalid_csrf_is_rejected_without_creating_asset` |
| TC-AUTH-05 | Logout | Session cleared; protected routes redirect to login | `test_logout_clears_the_authenticated_session` |
| TC-INV-01 | Create asset with required fields | Asset persists and detail page renders | `test_asset_manager_can_manage_assets`, `test_dashboard_shows_asset_counts` |
| TC-INV-02 | Missing required asset field / invalid date | Form rejected with validation error | `test_asset_creation_requires_tag_name_and_category`, `test_tc_01_*`, `test_tc_02_*` |
| TC-INV-03 | Duplicate asset tag / serial | Duplicate rejected without replacing existing asset | `test_asset_creation_rejects_duplicate_tag_and_serial` |
| TC-INV-04 | Search and status filtering | Only matching assets displayed | `test_asset_search_and_status_filter`, `test_tc_11_*` |
| TC-ALLOC-01 | Allocate and return asset | Status transition and history retained | `test_allocate_return_preserves_history_and_prevents_double_allocation` |
| TC-ALLOC-02 | Invalid allocation / return | Current state unchanged; informative error | `test_tc_08_*`, `test_tc_09_*` |
| TC-RET-01 | Retire available asset | Becomes retired and cannot be allocated | `test_tc_10_retired_asset_cannot_be_reallocated` |
| TC-RET-02 | Retire allocated asset | Retirement blocked | `test_asset_cannot_be_retired_while_allocated` |
| TC-LIFE-01 | Edit non-retired asset | Details updated; form CSRF protected | `test_edit_form_updates_persist` |
| TC-LIFE-02 | Edit invalid / duplicate / retired asset | Validation or HTTP 409; no unwanted change | `test_edit_rejects_duplicate_tag_and_serial`, `test_edit_rejects_invalid_data`, `test_retirement_preserves_history_and_blocks_changes` |
| TC-LIFE-03 | Transfer holder of allocated asset | Previous allocation closed; new current holder created | `test_transfer_keeps_allocation_history_and_return` |
| TC-LIFE-04 | Invalid transfer and unauthorized edit / transfer | State unchanged; denied to guests and read-only roles | `test_invalid_transfers_never_change_holder`, `test_anonymous_users_cannot_access_edit_or_transfer`, `test_read_only_roles_cannot_edit_or_transfer` |
| TC-LIFE-05 | Edit / transfer without CSRF | HTTP 400 | `test_edit_and_transfer_require_valid_csrf` |
| TC-SEC-01 | User and password policy | Reject invalid names / short passwords; salted hash used | `test_tc_04_*`, `test_tc_05_*`, `test_login_uses_salted_password_hash` |
| TC-DATA-01 | Database initialization / secret key | Repeatable initialization; rejects empty secret file | `test_tc_13_*`, `test_tc_06_*` |

The `TC-LIFE` group runs from the **S1-02 feature branch**; it is not yet an accepted main-branch feature until PR #5 is merged.

## Test execution method

- Unit tests: direct Python validation and secret-handling functions.
- Integration/system checks: Flask test client, temporary SQLite database, authenticated sessions, CSRF tokens.
- Coverage: `pytest-cov --cov=app --cov=sprint1_asset_lifecycle --cov-branch`.
- Source of evidence: JUnit XML test results and JSON coverage measured in the same GitHub Actions run.

## Deferred / not implemented

| Planned area | Test-case status |
|---|---|
| License renewal / software entitlements | Blocked — module not implemented |
| Warranty dates and expiry notification | Blocked — module not implemented |
| Maintenance plans and service history | Blocked — module not implemented |
| Alerts and compliance reporting | Blocked — module not implemented |
| Audit trail for edits / transfers (S1-03) | Pending teammate integration |
| CSV import/export and dashboard reports | Blocked — module not implemented |
| Performance, live UI UAT, backup/restore, multi-browser accessibility | Manual/environment validation pending |

**Acceptance rule:** A report may indicate passing automated tests while the overall system is **not yet fully validated**. Do not manufacture pass/fail results for blocked cases.
