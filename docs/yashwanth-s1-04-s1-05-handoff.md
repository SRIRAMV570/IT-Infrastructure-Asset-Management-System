# Sprint 1 Handoff — S1-04 and S1-05

**Owner:** @yashwanth00000  
**Sprint:** Sprint 1 (October 29–November 4, 2026)  
**Feature branch:** `feature/yashwanth-s1-dashboard-ux`

## S1-04 — Dashboard summaries and keyboard-accessible form feedback

### Implemented

- Added a category summary to the dashboard, grouped case-insensitively and ordered by category.
- Kept the existing all-assets and lifecycle-status totals and added status summary navigation.
- Made category summary rows link to the matching inventory search.
- Added explicit input identifiers and associated labels/help text to the asset registration form.
- Added accessible field-level feedback for required fields, duplicate asset tags, duplicate serial numbers, and invalid purchase dates using `aria-invalid`, `aria-describedby`, and alert text.
- Strengthened visible keyboard focus indicators for inputs, buttons, and links.
- Added dashboard and form-validation regression tests.

### Acceptance criteria mapping

| Acceptance criterion | Implementation / evidence |
|---|---|
| Dashboard totals and category summaries match stored data | Dashboard queries grouped category counts and lifecycle counts; tests cover multiple categories and empty inventory. |
| Category summaries are usable | Each category links to the inventory search for that category. |
| Key forms support keyboard navigation | Native form controls are retained; visible focus styles are provided for inputs, buttons, and links. |
| Validation errors are clear and field-associated | Required, duplicate, and date errors render beside the corresponding input with accessible ARIA relationships. |
| Automated tests cover count accuracy and invalid-form feedback | Regression tests added to `tests/test_app.py`. |

## S1-05 — Working increment validation and sprint demo handoff

### Validation status

- [x] Regression tests added for category totals, empty category summaries, field-level errors, duplicate identifiers, and keyboard focus styling.
- [x] GitHub Actions workflow exists and is configured to run `python -m pytest -q` on branch pushes and pull requests.
- [ ] Local `python -m pytest -q` execution: **not run in this session**. An attempt to clone the public repository failed because this environment could not resolve `github.com`. Run the command locally before merge.
- [x] PR GitHub Actions check: **passed** on October 30, 2026. The latest PR run executed `python -m pytest -q` and reported **32 passed in 6.78s**.
- [ ] Teammate approval: requested from @SharveshK1228; review is pending.
- [ ] One-minute demo video: not recorded or uploaded in this session.

### One-minute demo run sheet

Use synthetic records and a local development instance. Do not show real credentials or organizational data.

| Time | Demonstration |
|---|---|
| 0:00–0:10 | Sign in and open the dashboard. Point out all-assets and lifecycle status totals. |
| 0:10–0:22 | Show category totals and open a category row to filter the inventory. |
| 0:22–0:35 | Return to the dashboard, open asset registration, and use Tab/Shift+Tab to show visible keyboard focus. |
| 0:35–0:48 | Submit a duplicate asset tag to show the error beside the relevant field; point out that the entered values remain available for correction. |
| 0:48–1:00 | Correct the duplicate, save a synthetic asset, and return to the dashboard to show the updated totals. |

### Deviations and limitations

- The one-minute video still needs to be recorded by a team member using the running application and uploaded to the repository.
- Local pytest execution and manual browser verification remain outstanding; do not treat the passing CI run as a substitute for the required local/manual checks.
- The first CI run exposed an outdated duplicate-error assertion; the assertion was updated to verify the field-specific messages, and the subsequent PR run passed.
- This change is limited to Sprint 1 S1-04 and the S1-05 validation/demo handoff. Sprint 2 maintenance scheduling (S2-02) remains a separate planned item.
