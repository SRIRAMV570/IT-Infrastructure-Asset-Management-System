# ITAMS — Part-3 Testing & Submission Checklist

## Requirement-to-deliverable map

| Part-3 instruction | Project output |
|---|---|
| Update Sprint-affected test cases | [Part3_Test_Case_Document.md](Part3_Test_Case_Document.md) and `tests/test_part3_regression.py` |
| Complete testing according to Test Plan | GitHub Actions Part-3 QA job, plus listed manual validation still required |
| Unit Test Report | `Part3_Unit_Test_Report.md` (generated from JUnit test execution) |
| System Validation Report | `Part3_System_Validation_Report.md` (automated evidence + open UAT gaps) |
| Code Coverage Report | `Part3_Code_Coverage_Report.md` (measured statement coverage) |
| Branch Coverage Report | `Part3_Branch_Coverage_Report.md` (measured control-flow branches) |
| Upload all reports to docs | Part-3 QA workflow commits the four reports under `docs/` on the S1-02 branch (if Actions write access allows); also uploads downloadable workflow artifacts |
| Optional Sprint-3 | Not started; only create if genuine Sprint-1/2 spillover is agreed |

## Run window

The Part-3 assignment identifies **2–6 November 2026** as the formal testing window. A 29 October run is a **preliminary baseline**; rerun the workflow in the specified week and record the new timestamp. Do not backdate evidence.

## Repeat locally

```bash
python -m pip install -r requirements.txt pytest-cov
mkdir -p docs
python -m pytest -q --junitxml=docs/part3_junit.xml \
  --cov=app --cov=sprint1_asset_lifecycle --cov-branch \
  --cov-report=term-missing --cov-report=json:docs/part3_coverage.json \
  --cov-report=xml:docs/part3_coverage.xml
python scripts/generate_part3_reports.py \
  --junit docs/part3_junit.xml --coverage docs/part3_coverage.json
```

Generated JUnit and coverage machine files are CI artifacts, not source-controlled; the four human-readable Markdown reports are committed to `docs/`.

## Manual validation for 2–6 November

- Start Flask locally with synthetic test data; confirm login, 403 authorization and CSRF behavior in real browser.
- Check create/search/filter, allocation, direct transfer, return, retirement, and edit flows with screenshots.
- Verify error messages and DB history after each negative case.
- Measure performance/usability and backup/restore only against agreed test-plan thresholds and an actual test environment.
- Record defects with reproduction steps and retest outcomes.
- Reconcile pending audit events and any added Sprint-2 modules before system sign-off.

## Sign-off

Automated pass status does not constitute complete system acceptance. The team should attach browser/UAT evidence, document unresolved defects, and secure review before merging PR #5 into `main`.
