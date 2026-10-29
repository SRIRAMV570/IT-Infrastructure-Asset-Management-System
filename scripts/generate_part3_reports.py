"""Convert actual pytest/JUnit and branch-aware coverage evidence to Part-3 reports.

Run after pytest; the reports deliberately distinguish executed tests from
planned/unimplemented features and manual validation still outstanding.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET


REPORTS = {
    "unit": "Part3_Unit_Test_Report.md",
    "system": "Part3_System_Validation_Report.md",
    "code": "Part3_Code_Coverage_Report.md",
    "branch": "Part3_Branch_Coverage_Report.md",
}


def parse_junit(path):
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        outcome = "PASSED"
        if case.find("failure") is not None:
            outcome = "FAILED"
        elif case.find("error") is not None:
            outcome = "ERROR"
        elif case.find("skipped") is not None:
            outcome = "SKIPPED"
        cases.append({
            "name": case.get("name", "unnamed"),
            "file": case.get("classname", "unknown"),
            "outcome": outcome,
            "seconds": float(case.get("time", "0") or "0"),
        })
    return cases


def report_header(title, created, run_url, sha):
    return (
        "# " + title + "\n\n"
        + "**Project:** IT Infrastructure & Asset Management System (ITAMS)  \n"
        + "**Evidence generated (UTC):** " + created + "  \n"
        + "**Source commit:** `" + sha + "`  \n"
        + "**CI execution:** " + (run_url or "local run") + "  \n"
        + "**Basis:** actual pytest JUnit XML and pytest-cov JSON from the same run.\n\n"
    )


def pct(covered, total):
    if not total:
        return "N/A"
    return f"{(covered / total) * 100:.2f}%"


def status_for(cases, names):
    matched = [case for case in cases if any(name in case["name"] for name in names)]
    if not matched:
        return "NOT TESTED"
    if any(case["outcome"] in ("FAILED", "ERROR") for case in matched):
        return "FAIL"
    if any(case["outcome"] == "SKIPPED" for case in matched):
        return "PARTIAL"
    return "PASS (automated)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--junit", default="docs/part3_junit.xml")
    parser.add_argument("--coverage", default="docs/part3_coverage.json")
    parser.add_argument("--docs", default="docs")
    parser.add_argument("--sha", default="local")
    parser.add_argument("--run-url", default="")
    options = parser.parse_args()
    docs = Path(options.docs)
    docs.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cases = parse_junit(options.junit)
    data = json.loads(Path(options.coverage).read_text(encoding="utf-8"))
    totals = data["totals"]
    by_outcome = {status: sum(c["outcome"] == status for c in cases)
                  for status in ("PASSED", "FAILED", "ERROR", "SKIPPED")}
    total = len(cases)
    run_state = "PASS" if by_outcome["FAILED"] == by_outcome["ERROR"] == 0 else "FAIL"
    evidence = "\n".join(
        f"| {case['file']}::{case['name']} | {case['outcome']} | {case['seconds']:.3f} |"
        for case in cases
    )
    unit = report_header("Part-3 — Unit Test Report", now, options.run_url, options.sha)
    unit += (
        f"**Automated test result: {run_state}.** {total} executed; "
        f"{by_outcome['PASSED']} passed, {by_outcome['FAILED']} failed, "
        f"{by_outcome['ERROR']} errors, {by_outcome['SKIPPED']} skipped.\n\n"
        "The suite combines pure-function checks with Flask test-client integration "
        "and security regression tests. Test names indicate the verified behavior; "
        "these are not performance or live-deployment tests.\n\n"
        "| Executed test | Result | Runtime (seconds) |\n|---|---|---:|\n"
        + evidence + "\n\n"
        "Reproduce: `python -m pytest -q --cov=app "
        "--cov=sprint1_asset_lifecycle --cov-branch`.\n"
    )

    validation = [
        ("V-01", "Login and invalid credentials", ["test_invalid_login", "test_login_uses_salted"]),
        ("V-02", "Authentication, roles and logout", ["test_protected_pages", "test_employee_can_read", "test_read_only_roles", "test_logout"]),
        ("V-03", "Asset registration and duplicate/invalid data", ["test_asset_creation", "test_invalid_purchase", "test_edit_rejects"]),
        ("V-04", "Inventory search, filters and dashboard", ["test_dashboard", "test_asset_search", "test_tc_11"]),
        ("V-05", "Asset allocation, return and retirement", ["test_allocate_return", "test_asset_cannot", "test_retirement", "test_tc_10"]),
        ("V-06", "Asset editing and direct transfers (Sprint-1 S1-02)", ["test_edit_form", "test_transfer_keeps", "test_invalid_transfers"]),
        ("V-07", "CSRF and unauthorized lifecycle changes", ["test_mutating", "test_edit_and_transfer", "test_tc_12"]),
        ("V-08", "Database creation and stable app configuration", ["test_tc_13", "test_development_secret"]),
    ]
    system = report_header("Part-3 — System Validation Report", now, options.run_url, options.sha)
    system += (
        f"**Automated validation status:** {run_state} for exercised routes and functions. "
        "**Full system sign-off: NOT COMPLETE.**\n\n"
        "The automated checks use the Flask test client with an isolated temporary "
        "SQLite database. This is integration-level evidence, not manual UAT in a "
        "deployed browser environment.\n\n"
        "| ID | Validation area | Evidence status |\n|---|---|---|\n"
    )
    for code, title, checks in validation:
        system += f"| {code} | {title} | {status_for(cases, checks)} |\n"
    system += (
        "\n## Deferred or unavailable acceptance areas\n\n"
        "| Area | Status / reason |\n|---|---|\n"
        "| Software license and warranty management | NOT TESTED — not available in the current implementation |\n"
        "| Maintenance and overdue alerts | NOT TESTED — not available in the current implementation |\n"
        "| Reporting and CSV import/export | NOT TESTED — not available in the current implementation |\n"
        "| Audit-event persistence | NOT TESTED — awaits S1-03 integration |\n"
        "| Browser UAT / accessibility / cross-browser | NOT EXECUTED — manual test window required |\n"
        "| Performance, backup/restore and security assessment | NOT EXECUTED — separate environment and criteria required |\n"
        "\n## Decision\n\n"
        "Automated regression evidence supports the implemented functions only. "
        "Do not mark the complete SRS or Test Plan as accepted until missing modules "
        "are implemented and manual validation is signed off.\n"
    )

    code = report_header("Part-3 — Code Coverage Report", now, options.run_url, options.sha)
    code += (
        "Coverage tool: pytest-cov / coverage.py. Scope: executable Python source in "
        "`app.py` and `sprint1_asset_lifecycle.py`; templates, CSS and unimplemented "
        "features are excluded from this percentage.\n\n"
        f"**Overall statement coverage: {pct(totals.get('covered_lines',0), totals.get('num_statements',0))}** "
        f"({totals.get('covered_lines',0)} / {totals.get('num_statements',0)} statements).\n\n"
        "| Source | Covered statements | Total statements | Statement coverage | Missing lines |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for filename, content in sorted(data.get("files", {}).items()):
        summary = content["summary"]
        code += (
            f"| `{filename}` | {summary.get('covered_lines',0)} | "
            f"{summary.get('num_statements',0)} | "
            f"{pct(summary.get('covered_lines',0), summary.get('num_statements',0))} | "
            f"{summary.get('missing_lines',0)} |\n"
        )
    code += (
        "\n**Interpretation:** This is measured Python statement coverage, not a "
        "proxy for requirements completion, functional correctness or UI test coverage.\n"
    )

    branch = report_header("Part-3 — Branch Coverage Report", now, options.run_url, options.sha)
    branch += (
        "Branch measurement uses `--cov-branch` (conditional control-flow arcs). "
        "A branch percentage is not the same as feature completeness.\n\n"
        f"**Overall branch coverage: {pct(totals.get('covered_branches',0), totals.get('num_branches',0))}** "
        f"({totals.get('covered_branches',0)} / {totals.get('num_branches',0)} measured arcs).\n\n"
        "| Source | Covered branches | Total branches | Branch coverage | Missing branches |\n"
        "|---|---:|---:|---:|---:|\n"
    )
    for filename, content in sorted(data.get("files", {}).items()):
        summary = content["summary"]
        branch += (
            f"| `{filename}` | {summary.get('covered_branches',0)} | "
            f"{summary.get('num_branches',0)} | "
            f"{pct(summary.get('covered_branches',0), summary.get('num_branches',0))} | "
            f"{summary.get('missing_branches',0)} |\n"
        )
    branch += (
        "\n**Follow-up:** Prioritize missed decision paths (authorization denial, "
        "invalid inputs, conflict handling, and concurrency where reproducible). "
        "Use the CI coverage artifact for detailed missing arcs.\n"
    )
    for name, content in zip(REPORTS.values(), (unit, system, code, branch)):
        (docs / name).write_text(content, encoding="utf-8")
    print(f"Generated {len(REPORTS)} reports; {total} test cases, result {run_state}")


if __name__ == "__main__":
    main()
