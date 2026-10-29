# Part-3 — Branch Coverage Report

**Project:** IT Infrastructure & Asset Management System (ITAMS)  
**Evidence generated (UTC):** 2026-10-29 06:22:55 UTC  
**Source commit:** `90cfc4010c614775e1603c86c44d330150afcac9`  
**CI execution:** https://github.com/SRIRAMV570/IT-Infrastructure-Asset-Management-System/actions/runs/40828822838  
**Basis:** actual pytest JUnit XML and pytest-cov JSON from the same run.

Branch measurement uses `--cov-branch` (conditional control-flow arcs). A branch percentage is not the same as feature completeness.

**Overall branch coverage: 80.00%** (80 / 100 measured arcs).

| Source | Covered branches | Total branches | Branch coverage | Missing branches |
|---|---:|---:|---:|---:|
| `app.py` | 61 | 76 | 80.26% | 15 |
| `sprint1_asset_lifecycle.py` | 19 | 24 | 79.17% | 5 |

**Follow-up:** Prioritize missed decision paths (authorization denial, invalid inputs, conflict handling, and concurrency where reproducible). Use the CI coverage artifact for detailed missing arcs.
