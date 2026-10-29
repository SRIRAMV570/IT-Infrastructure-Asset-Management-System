# IT Infrastructure & Asset Management System (ITAMS)

## Project Overview

The **IT Infrastructure & Asset Management System (ITAMS)** is designed to help an organization maintain a centralized record of its IT assets and manage their lifecycle. The system covers hardware, software, licenses, warranties, maintenance, asset allocation, alerts, reporting, and compliance-related information.

It aims to make asset records easier to track, reduce missed expiry or maintenance dates, and improve visibility into asset ownership and status.

## Problem Statement

Organizations need a reliable way to track IT hardware and software, software licenses, warranties, maintenance schedules, and asset allocation. Without a centralized system, records can become outdated, renewals may be missed, maintenance may be delayed, and compliance issues may go unnoticed.

ITAMS addresses this problem by maintaining structured asset records and generating alerts for license or warranty expiry, overdue maintenance, and incomplete compliance information.

## Objectives

- Maintain a centralized inventory of hardware and software assets.
- Track asset allocation, returns, transfers, and retirement.
- Record software license entitlements, expiry dates, and renewal status.
- Track warranty details and coverage dates.
- Schedule maintenance and preserve repair/service history.
- Generate alerts for upcoming or overdue expiry and maintenance events.
- Provide dashboards and reports for inventory, allocation, maintenance, and compliance.
- Enforce role-based access and retain audit history for important changes.

## Main Features

- **Asset Inventory:** Create, update, search, filter, and retire asset records.
- **Asset Allocation:** Assign assets to employees, departments, teams, or locations and record returns or transfers.
- **License Management:** Store software product, entitlement, expiry, and renewal information.
- **Warranty Tracking:** Maintain warranty references, providers, and coverage dates.
- **Maintenance Management:** Schedule maintenance and record completed service activities.
- **Alerts:** Identify upcoming or expired licenses and warranties, overdue maintenance, and incomplete records.
- **Dashboard and Reports:** Summarize asset status and generate inventory, allocation, expiry, maintenance, and compliance reports.
- **Audit Trail:** Record important actions with actor and timestamp details.
- **Role-Based Access Control:** Separate permissions for administrators, IT/asset managers, department managers, employees, and auditors.
- **Data Import and Export:** Support validated CSV import and report export where implemented.

## User Roles

| Role | Description |
|---|---|
| System Administrator | Manages users, roles, configuration, and asset records. |
| Asset Manager / IT Administrator | Manages inventory, allocations, licenses, warranties, and maintenance. |
| Department Manager | Views departmental assets and may approve allocations or transfers if enabled. |
| Employee / Asset Holder | Views assigned assets and can submit return or fault requests where implemented. |
| Auditor / Read-only User | Reviews reports, compliance information, and audit history without modifying records. |

## High-Level Architecture

The proposed design follows a **layered modular architecture**:

1. **User Interface:** Browser-based screens for inventory, allocations, alerts, dashboards, and reports.
2. **Web Controller / API Layer:** Receives requests and checks authentication and permissions.
3. **Business Services:** Handles asset inventory, allocation, licenses, warranties, maintenance, alerts, reporting, and audit operations.
4. **Data Access Layer:** Validates and persists data through repositories or an ORM.
5. **Relational Database:** Stores users, roles, assets, allocations, licenses, warranties, maintenance records, alerts, and audit events.
6. **Optional Notification Service:** Sends email alerts if configured; in-app alerts remain part of the intended system.

The application is implemented as a modular Flask monolith to keep deployment and maintenance manageable.

## Technology Stack

- **Backend:** Python 3.12+ with Flask
- **Database:** SQLite
- **Frontend:** Server-rendered HTML templates and CSS
- **Tests:** pytest and Flask's test client

## Authentication and roles

All application pages require a signed-in user. Accounts are created from the command line; there is no public registration page. Create the first administrator from the repository root:

```powershell
flask --app app:create_app create-admin --username admin
```

The CLI prompts for a password and confirmation. Passwords must be at least 12 characters and are stored as salted hashes. After the first administrator is created, add accounts using one of these roles:

```powershell
flask --app app:create_app create-user --username assetmanager --role asset_manager
flask --app app:create_app create-user --username auditor1 --role auditor
```

`admin` and `asset_manager` can register and manage assets, allocate, return, and retire them. `department_manager`, `employee`, and `auditor` have read-only dashboard and inventory access. Authorization is enforced on the server, not just by hiding controls in the UI. Mutating forms, including login, also require a CSRF token.

For local development, the session signing key is generated once and saved in the ignored `instance/.flask_secret_key` file. For deployment, set a strong `FLASK_SECRET_KEY` through the hosting environment, serve the app only over HTTPS, and set `SESSION_COOKIE_SECURE=1`. Do not commit the key or use the development server for public deployment.

## Core Data Entities

The system is expected to manage records such as:

- **Users and Roles**
- **Assets** — asset ID, name, category, tag, serial number where applicable, status, and location
- **Allocations** — asset, assignee, allocation date, return date, and history
- **Software Licenses** — product, entitlement quantity, expiry date, and renewal status
- **Warranties** — provider/reference and coverage dates
- **Maintenance Records** — due date, priority, responsible team, status, and service history
- **Alerts** — alert type, related record, due date, status, and resolution history
- **Audit Events** — actor, timestamp, action, and affected record

## Alerts and Compliance

The intended alerting functionality includes:

- Upcoming or passed software license expiry
- Upcoming or passed warranty expiry
- Overdue maintenance
- Missing mandatory asset or compliance information
- License usage exceeding recorded entitlement, when usage data is available

Expiry thresholds and notification channels should be configured according to project requirements.

## Security Considerations

- Require authentication for protected functions.
- Enforce role-based permissions on the server.
- Use HTTPS/TLS in deployed environments.
- Store passwords using an appropriate salted password-hashing algorithm.
- Validate inputs and use parameterized database operations.
- Do not log passwords, session tokens, or full license secrets.
- Record important changes in an audit trail.
- Use synthetic data for development and testing; avoid real credentials or confidential organizational information.

## Documentation

The project documentation includes:

- **Software Requirements Specification (SRS):** Functional and non-functional requirements, security requirements, acceptance criteria, use-case model, and requirements traceability matrix.
- **Software Architecture and Design Specification (SAD):** Architecture, components, API design, workflow sequences, risks, and security design.
- **Software Test Plan (STP):** Test scope, approach, test cases, environment, schedule, responsibilities, and acceptance criteria.

## Testing Overview

Representative tests should cover:

- Authentication and role-based authorization
- Asset creation, validation, search, and filtering
- Allocation, return, transfer, and retirement
- License and warranty records
- Maintenance scheduling and history
- Expiry and overdue-maintenance alerts
- Reports and CSV import/export where implemented
- Audit trail and sensitive-data handling
- Performance, usability, and backup/restore procedures where supported

Test cases in the plan are proposed cases. Record actual results only after executing them against the implementation.

## Getting Started

Use Python 3.12 or newer. From the repository root, create and activate a virtual environment, install dependencies, create the initial administrator, and start the local development server:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
flask --app app:create_app create-admin --username admin
python app.py
```

Open <http://127.0.0.1:5000> and sign in with the administrator account you created. The SQLite database is created automatically at `instance/itams.sqlite3`.

Run the automated tests locally before proposing changes:

```powershell
python -m pytest -q
```

## Current Implementation

The initial application source supports asset registration and validation, inventory search and status filtering, an inventory dashboard, allocation and return history, and retirement of available assets. Automated tests cover these behaviors.

Authentication and role-based permissions, asset editing, license and warranty management, maintenance scheduling, alerts, reporting, and audit history remain to be implemented. This prototype is for local development and evaluation only; do not expose it to an untrusted network or use it for real organizational data until authentication, authorization, and deployment security are added.
7. Verify login, asset creation, allocation, expiry alerts, and reporting.

Do not commit passwords, API keys, database credentials, or other secrets to version control.

## Project Team

- **SRI RAM V**
- **Sharvesh**
- **Yashwanth**
- **Shreyan Ganesh**

## Project Status

The SRS, SAD, and test plan describe the broader target system. Keep implementation and test status up to date as additional features are developed.

## License

No open-source license has been specified for this project. Add a license only after the project team decides how the code may be used and redistributed.
