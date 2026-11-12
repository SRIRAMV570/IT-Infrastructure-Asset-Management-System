import re
import sqlite3
from datetime import date, timedelta

import pytest

from app import create_app


ADMIN_USERNAME = "maintenance-admin"
ADMIN_PASSWORD = "MaintenanceAdminPassword42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "maintenance-test.sqlite3"),
            "SECRET_KEY": "test-only-secret",
        }
    )
    result = application.test_cli_runner().invoke(
        args=["create-admin", "--username", ADMIN_USERNAME],
        input=f"{ADMIN_PASSWORD}\n{ADMIN_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    return application


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    login(test_client, ADMIN_USERNAME, ADMIN_PASSWORD)
    return test_client


def csrf_token(client, path="/"):
    response = client.get(path)
    match = re.search(
        r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)
    )
    assert match, f"No CSRF token found on {path}"
    return match.group(1)


def login(client, username, password):
    token = csrf_token(client, "/login")
    return client.post(
        "/login",
        data={"csrf_token": token, "username": username, "password": password},
        follow_redirects=True,
    )


def post_form(client, path, data=None, follow_redirects=False):
    values = dict(data or {})
    values["csrf_token"] = csrf_token(client)
    return client.post(path, data=values, follow_redirects=follow_redirects)


def add_asset(client):
    response = post_form(
        client,
        "/assets/new",
        {
            "asset_tag": "MAINT-001",
            "name": "Maintenance test laptop",
            "category": "Laptop",
            "manufacturer": "Example",
            "model": "TestBook",
            "serial_number": "MAINT-SER-001",
            "location": "IT Lab",
        },
    )
    assert response.status_code == 302
    match = re.search(r"/assets/(\d+)$", response.headers["Location"])
    assert match
    return int(match.group(1))


def create_schedule(client, asset_id, **overrides):
    values = {
        "asset_id": str(asset_id),
        "title": "Quarterly hardware inspection",
        "due_date": (date.today() + timedelta(days=7)).isoformat(),
        "priority": "high",
        "assigned_to": "IT Support",
        "notes": "Inspect fan, ports, and battery condition.",
    }
    values.update(overrides)
    return post_form(client, "/maintenance/new", values)


def test_maintenance_schedule_is_created_and_visible(client):
    asset_id = add_asset(client)

    response = create_schedule(client, asset_id)
    listing = client.get("/maintenance")

    assert response.status_code == 302
    assert f"asset_id={asset_id}" in response.headers["Location"]
    assert listing.status_code == 200
    assert b"Quarterly hardware inspection" in listing.data
    assert b"MAINT-001" in listing.data
    assert b"Upcoming" in listing.data
    assert b"IT Support" in listing.data


def test_invalid_due_date_and_retired_asset_are_rejected(client, app):
    asset_id = add_asset(client)
    invalid_date = create_schedule(client, asset_id, due_date="31-12-2026")

    assert invalid_date.status_code == 400
    assert b"Enter a valid due date." in invalid_date.data

    with app.app_context():
        app_db = sqlite3.connect(app.config["DATABASE"])
        app_db.execute("UPDATE assets SET status='retired' WHERE id=?", (asset_id,))
        app_db.commit()
        app_db.close()

    retired = create_schedule(
        client, asset_id, due_date=(date.today() + timedelta(days=3)).isoformat()
    )
    assert retired.status_code == 400
    assert b"Retired assets cannot be scheduled" in retired.data


def test_overdue_maintenance_is_identified_from_due_date(client):
    asset_id = add_asset(client)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    response = create_schedule(client, asset_id, due_date=yesterday)
    listing = client.get("/maintenance")

    assert response.status_code == 302
    assert b"Overdue" in listing.data


def test_start_and_complete_preserve_service_history(client, app):
    asset_id = add_asset(client)
    created = create_schedule(client, asset_id)
    assert created.status_code == 302

    with app.app_context():
        connection = sqlite3.connect(app.config["DATABASE"])
        maintenance_id = connection.execute(
            "SELECT id FROM maintenance_schedules WHERE asset_id=?", (asset_id,)
        ).fetchone()[0]
        connection.close()

    started = post_form(client, f"/maintenance/{maintenance_id}/start")
    assert started.status_code == 302
    assert b"In Progress" in client.get("/maintenance").data

    completion_path = f"/maintenance/{maintenance_id}/complete"
    completed = post_form(
        client,
        completion_path,
        {
            "service_date": date.today().isoformat(),
            "performed_by": "Facilities technician",
            "notes": "Replaced the cooling fan and verified normal operation.",
        },
        follow_redirects=True,
    )
    listing = client.get(f"/maintenance?asset_id={asset_id}")

    assert completed.status_code == 200
    assert b"Maintenance completed and service history recorded." in completed.data
    assert b"Completed" in listing.data
    assert b"Replaced the cooling fan" in listing.data
    assert b"Facilities technician" in listing.data

    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        status = connection.execute(
            "SELECT status FROM maintenance_schedules WHERE id=?", (maintenance_id,)
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM maintenance_service_history WHERE maintenance_id=?",
            (maintenance_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "completed"
    assert history_count == 1


def test_invalid_service_record_does_not_complete_schedule(client, app):
    asset_id = add_asset(client)
    create_schedule(client, asset_id)

    connection = sqlite3.connect(app.config["DATABASE"])
    maintenance_id = connection.execute(
        "SELECT id FROM maintenance_schedules WHERE asset_id=?", (asset_id,)
    ).fetchone()[0]
    connection.close()

    response = post_form(
        client,
        f"/maintenance/{maintenance_id}/complete",
        {
            "service_date": "not-a-date",
            "performed_by": "",
            "notes": "",
        },
    )
    assert response.status_code == 400
    assert b"Enter a valid service date." in response.data
    assert b"service notes" in response.data.lower()

    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        status = connection.execute(
            "SELECT status FROM maintenance_schedules WHERE id=?", (maintenance_id,)
        ).fetchone()[0]
        history_count = connection.execute(
            "SELECT COUNT(*) FROM maintenance_service_history WHERE maintenance_id=?",
            (maintenance_id,),
        ).fetchone()[0]
    finally:
        connection.close()
    assert status == "scheduled"
    assert history_count == 0


def test_read_only_employee_can_view_but_cannot_manage_maintenance(app):
    password = "EmployeeMaintenancePassword42!"
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", "maintenance-employee", "--role", "employee"],
        input=f"{password}\n{password}\n",
    )
    assert result.exit_code == 0, result.output

    employee = app.test_client()
    login(employee, "maintenance-employee", password)

    assert employee.get("/maintenance").status_code == 200
    assert employee.get("/maintenance/new").status_code == 403
    denied = post_form(
        employee,
        "/maintenance/new",
        {
            "asset_id": "1",
            "title": "Unauthorized work",
            "due_date": date.today().isoformat(),
            "priority": "low",
            "assigned_to": "Employee",
        },
    )
    assert denied.status_code == 403


def test_service_history_rows_are_immutable(client, app):
    asset_id = add_asset(client)
    create_schedule(client, asset_id)

    connection = sqlite3.connect(app.config["DATABASE"])
    maintenance_id = connection.execute(
        "SELECT id FROM maintenance_schedules WHERE asset_id=?", (asset_id,)
    ).fetchone()[0]
    connection.close()

    post_form(
        client,
        f"/maintenance/{maintenance_id}/complete",
        {
            "service_date": date.today().isoformat(),
            "performed_by": "Facilities technician",
            "notes": "Cleaned internal filters and tested device.",
        },
    )

    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE maintenance_service_history SET notes='changed' WHERE maintenance_id=?",
                (maintenance_id,),
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM maintenance_service_history WHERE maintenance_id=?",
                (maintenance_id,),
            )
        connection.rollback()
    finally:
        connection.close()



def test_maintenance_status_filter_returns_only_matching_schedules(client, app):
    asset_id = add_asset(client)
    create_schedule(client, asset_id, title="Scheduled inspection")
    create_schedule(client, asset_id, title="Work to start")

    connection = sqlite3.connect(app.config["DATABASE"])
    maintenance_id = connection.execute(
        "SELECT id FROM maintenance_schedules WHERE title=?",
        ("Work to start",),
    ).fetchone()[0]
    connection.close()
    assert post_form(client, f"/maintenance/{maintenance_id}/start").status_code == 302

    scheduled = client.get("/maintenance?status=scheduled")
    in_progress = client.get("/maintenance?status=in_progress")

    assert scheduled.status_code == 200
    assert b"Scheduled inspection" in scheduled.data
    assert b"Work to start" not in scheduled.data
    assert in_progress.status_code == 200
    assert b"Work to start" in in_progress.data
    assert b"Scheduled inspection" not in in_progress.data
