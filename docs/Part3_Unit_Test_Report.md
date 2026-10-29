# Part-3 — Unit Test Report

**Project:** IT Infrastructure & Asset Management System (ITAMS)  
**Evidence generated (UTC):** 2026-10-29 06:26:39 UTC  
**Source commit:** `20cd695519067ed7e5a3841f4b1b42731507d81a`  
**CI execution:** https://github.com/SRIRAMV570/IT-Infrastructure-Asset-Management-System/actions/runs/40829198896  
**Basis:** actual pytest JUnit XML and pytest-cov JSON from the same run.

**Automated test result: PASS.** 47 executed; 47 passed, 0 failed, 0 errors, 0 skipped.

The suite combines pure-function checks with Flask test-client integration and security regression tests. Test names indicate the verified behavior; these are not performance or live-deployment tests.

| Executed test | Result | Runtime (seconds) |
|---|---|---:|
| tests.test_app::test_dashboard_shows_asset_counts | PASSED | 0.257 |
| tests.test_app::test_asset_creation_requires_tag_name_and_category | PASSED | 0.205 |
| tests.test_app::test_asset_creation_rejects_duplicate_tag_and_serial | PASSED | 0.227 |
| tests.test_app::test_invalid_purchase_date_is_rejected | PASSED | 0.204 |
| tests.test_app::test_asset_search_and_status_filter | PASSED | 0.228 |
| tests.test_app::test_allocate_return_preserves_history_and_prevents_double_allocation | PASSED | 0.224 |
| tests.test_app::test_asset_cannot_be_retired_while_allocated | PASSED | 0.216 |
| tests.test_app::test_protected_pages_redirect_anonymous_users_to_login | PASSED | 0.096 |
| tests.test_app::test_invalid_login_is_generic_and_does_not_authenticate | PASSED | 0.179 |
| tests.test_app::test_login_uses_salted_password_hash | PASSED | 0.265 |
| tests.test_app::test_employee_can_read_but_cannot_create_or_allocate_assets | PASSED | 0.381 |
| tests.test_app::test_mutating_requests_require_a_valid_csrf_token | PASSED | 0.207 |
| tests.test_app::test_logout_clears_the_authenticated_session | PASSED | 0.201 |
| tests.test_app::test_read_only_roles_cannot_register_assets[department_manager] | PASSED | 0.362 |
| tests.test_app::test_read_only_roles_cannot_register_assets[auditor] | PASSED | 0.354 |
| tests.test_app::test_create_admin_is_bootstrap_only | PASSED | 0.091 |
| tests.test_app::test_user_creation_requires_admin_and_valid_password | PASSED | 0.014 |
| tests.test_app::test_development_secret_is_stable_between_app_starts | PASSED | 0.001 |
| tests.test_app::test_asset_manager_can_manage_assets | PASSED | 0.291 |
| tests.test_part3_regression::test_tc_01_required_asset_fields_are_validated[asset_tag] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_01_required_asset_fields_are_validated[name] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_01_required_asset_fields_are_validated[category] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_02_invalid_purchase_dates_are_rejected[bad-date] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_02_invalid_purchase_dates_are_rejected[2026-02-30] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_02_invalid_purchase_dates_are_rejected[2026/01/01] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_03_valid_optional_purchase_date_is_accepted | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_04_usernames_outside_policy_are_rejected[aa] | PASSED | 0.001 |
| tests.test_part3_regression::test_tc_04_usernames_outside_policy_are_rejected[space name] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_04_usernames_outside_policy_are_rejected[bad/name] | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_05_short_password_is_rejected | PASSED | 0.000 |
| tests.test_part3_regression::test_tc_06_empty_development_secret_is_rejected | PASSED | 0.001 |
| tests.test_part3_regression::test_tc_07_unknown_asset_detail_returns_404 | PASSED | 0.198 |
| tests.test_part3_regression::test_tc_08_blank_assignee_does_not_allocate_asset | PASSED | 0.219 |
| tests.test_part3_regression::test_tc_09_return_without_allocation_is_denied | PASSED | 0.234 |
| tests.test_part3_regression::test_tc_10_retired_asset_cannot_be_reallocated | PASSED | 0.222 |
| tests.test_part3_regression::test_tc_11_search_by_location_and_invalid_status_fallback | PASSED | 0.229 |
| tests.test_part3_regression::test_tc_12_invalid_csrf_is_rejected_without_creating_asset | PASSED | 0.202 |
| tests.test_part3_regression::test_tc_13_schema_is_safe_to_initialize_twice | PASSED | 0.019 |
| tests.test_sprint1_lifecycle::test_edit_form_updates_persist | PASSED | 0.228 |
| tests.test_sprint1_lifecycle::test_edit_rejects_duplicate_tag_and_serial | PASSED | 0.234 |
| tests.test_sprint1_lifecycle::test_edit_rejects_invalid_data | PASSED | 0.228 |
| tests.test_sprint1_lifecycle::test_transfer_keeps_allocation_history_and_return | PASSED | 0.232 |
| tests.test_sprint1_lifecycle::test_invalid_transfers_never_change_holder | PASSED | 0.238 |
| tests.test_sprint1_lifecycle::test_retirement_preserves_history_and_blocks_changes | PASSED | 0.281 |
| tests.test_sprint1_lifecycle::test_anonymous_users_cannot_access_edit_or_transfer | PASSED | 0.213 |
| tests.test_sprint1_lifecycle::test_read_only_roles_cannot_edit_or_transfer | PASSED | 0.402 |
| tests.test_sprint1_lifecycle::test_edit_and_transfer_require_valid_csrf | PASSED | 0.216 |

Reproduce: `python -m pytest -q --cov=app --cov=sprint1_asset_lifecycle --cov-branch`.
