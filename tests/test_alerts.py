"""S2-03 alert threshold, deduplication, authorization and history tests."""
import re
import sqlite3
from datetime import date, timedelta

import pytest

from app import create_app, get_db


ADMIN_PASSWORD = "CorrectHorseBatteryStaple42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "alerts.sqlite3"),
        "SECRET_KEY": "test-alert-secret",
    })
    result = application.test_cli_runner().invoke(
        args=["create-admin", "--username", "admin"],
        input=f"{ADMIN_PASSWORD}\n{ADMIN_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    return application


def csrf_token(client, path="/"):
    response = client.get(path)
    match = re.search(
        r'name="csrf_token" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match, f"CSRF token missing from {path}"
    return match.group(1)


def login(client, username="admin", password=ADMIN_PASSWORD):
    response = client.post(
        "/login",
        data={
            "csrf_token": csrf_token(client, "/login"),
            "username": username,
            "password": password,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    return response


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    login(test_client)
    return test_client


def post_form(client, path, values=None, follow_redirects=True):
    payload = dict(values or {})
    payload["csrf_token"] = csrf_token(client)
    return client.post(path, data=payload, follow_redirects=follow_redirects)


def add_asset(client, tag="LAP-001", **overrides):
    values = {
        "asset_tag": tag,
        "name": "Developer laptop",
        "category": "Laptop",
        "manufacturer": "",
        "model": "",
        "serial_number": "",
        "location": "",
        "purchase_date": "",
    }
    values.update(overrides)
    response = post_form(
        client, "/assets/new", values, follow_redirects=False
    )
    assert response.status_code == 302, response.get_data(as_text=True)
    return int(response.headers["Location"].rstrip("/").rsplit("/", 1)[-1])


def seed_source_rows(app, table, rows):
    with app.app_context():
        db = get_db()
        for values in rows:
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            db.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
        db.commit()


def get_alerts(app):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM alerts ORDER BY id"
        ).fetchall()


def create_user(app, username, role="employee"):
    password = "EmployeeAlertsPassword42!"
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", username, "--role", role],
        input=f"{password}\n{password}\n",
    )
    assert result.exit_code == 0, result.output
    with app.app_context():
        user_id = get_db().execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()["id"]
    return user_id, password


def test_license_and_warranty_threshold_boundaries(client, app):
    asset_id = add_asset(
        client,
        manufacturer="Example",
        model="Model A",
        serial_number="SER-001",
        location="Room 1",
        purchase_date="2026-01-01",
    )
    today = date.today()
    seed_source_rows(app, "software_licenses", [
        {
            "asset_id": asset_id,
            "product_name": "Expiring Suite",
            "expiry_date": (today + timedelta(days=30)).isoformat(),
            "renewal_status": "active",
        },
        {
            "asset_id": asset_id,
            "product_name": "Not Yet Due Suite",
            "expiry_date": (today + timedelta(days=31)).isoformat(),
            "renewal_status": "active",
        },
    ])
    seed_source_rows(app, "warranties", [
        {
            "asset_id": asset_id,
            "provider": "Example OEM",
            "start_date": (today - timedelta(days=365)).isoformat(),
            "end_date": (today + timedelta(days=30)).isoformat(),
        },
        {
            "asset_id": asset_id,
            "provider": "Future OEM",
            "start_date": (today - timedelta(days=30)).isoformat(),
            "end_date": (today + timedelta(days=31)).isoformat(),
        },
    ])

    result = post_form(client, "/alerts/generate")
    assert result.status_code == 200
    alerts = get_alerts(app)
    assert {row["alert_type"] for row in alerts} == {
        "license_expiry", "warranty_expiry"
    }
    assert len(alerts) == 2
    assert all(row["status"] == "open" for row in alerts)


def test_overdue_maintenance_and_incomplete_asset_alerts(client, app):
    asset_id = add_asset(client, tag="LAP-INCOMPLETE")
    today = date.today()
    seed_source_rows(app, "maintenance_schedules", [
        {
            "asset_id": asset_id,
            "title": "Overdue inspection",
            "due_date": (today - timedelta(days=1)).isoformat(),
            "priority": "high",
            "status": "scheduled",
            "assigned_to": "IT Support",
        },
        {
            "asset_id": asset_id,
            "title": "Due today inspection",
            "due_date": today.isoformat(),
            "priority": "medium",
            "status": "scheduled",
            "assigned_to": "IT Support",
        },
    ])

    result = post_form(client, "/alerts/generate")
    assert result.status_code == 200
    alerts = get_alerts(app)
    assert {row["alert_type"] for row in alerts} == {
        "maintenance_overdue", "incomplete_record"
    }
    incomplete = next(row for row in alerts if row["alert_type"] == "incomplete_record")
    assert "manufacturer" in incomplete["message"]
    assert "serial number" in incomplete["message"]
    maintenance = next(row for row in alerts if row["alert_type"] == "maintenance_overdue")
    assert maintenance["severity"] == "medium"
    assert maintenance["due_date"] == (today - timedelta(days=1)).isoformat()


def test_repeated_generation_does_not_duplicate_active_alerts(client, app):
    asset_id = add_asset(client, manufacturer="Example", model="Model A",
                         serial_number="SER-001", location="Room 1",
                         purchase_date="2026-01-01")
    seed_source_rows(app, "software_licenses", [{
        "asset_id": asset_id,
        "product_name": "Design Suite",
        "expiry_date": (date.today() + timedelta(days=5)).isoformat(),
        "renewal_status": "renewal_pending",
    }])

    first = post_form(client, "/alerts/generate")
    second = post_form(client, "/alerts/generate")
    assert b"1 new alert" in first.data
    assert b"0 new alert" in second.data
    assert len(get_alerts(app)) == 1
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM alert_history WHERE event_type='generated'"
        ).fetchone()[0] == 1


def test_alert_acknowledge_assign_resolve_history_and_audit(client, app):
    add_asset(client)
    post_form(client, "/alerts/generate")
    alert = get_alerts(app)[0]
    employee_id, employee_password = create_user(app, "alert-employee")

    acknowledged = post_form(
        client, f"/alerts/{alert['id']}/acknowledge"
    )
    assert acknowledged.status_code == 200
    assigned = post_form(
        client,
        f"/alerts/{alert['id']}/assign",
        {"user_id": str(employee_id)},
    )
    assert assigned.status_code == 200
    resolved = post_form(
        client,
        f"/alerts/{alert['id']}/resolve",
        {"resolution_notes": "Asset record details have been completed."},
    )
    assert resolved.status_code == 200

    with app.app_context():
        db = get_db()
        current = db.execute(
            "SELECT status, assigned_username, resolution_notes FROM alerts WHERE id=?",
            (alert["id"],),
        ).fetchone()
        history = db.execute(
            """SELECT event_type, actor_username, from_status, to_status, created_at
               FROM alert_history WHERE alert_id=? ORDER BY id""",
            (alert["id"],),
        ).fetchall()
        actions = db.execute(
            "SELECT action FROM audit_events WHERE target_type='alert' AND target_id=? ORDER BY id",
            (alert["id"],),
        ).fetchall()

    assert current["status"] == "resolved"
    assert current["assigned_username"] == "alert-employee"
    assert current["resolution_notes"] == "Asset record details have been completed."
    assert [row["event_type"] for row in history] == [
        "generated", "acknowledged", "assigned", "resolved"
    ]
    assert [row["to_status"] for row in history] == [
        "open", "acknowledged", "assigned", "resolved"
    ]
    assert all(row["actor_username"] == "admin" for row in history)
    assert all(row["created_at"] for row in history)
    assert [row["action"] for row in actions] == [
        "alert.generated", "alert.acknowledged", "alert.assigned", "alert.resolved"
    ]

    duplicate_resolve = post_form(
        client, f"/alerts/{alert['id']}/resolve",
        {"resolution_notes": "Try again."}, follow_redirects=False,
    )
    assert duplicate_resolve.status_code == 409
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) FROM alert_history WHERE alert_id=?",
            (alert["id"],),
        ).fetchone()[0] == 4


def test_only_asset_managers_can_generate_or_manage_alerts(app, client):
    add_asset(client)
    alert_id = None
    post_form(client, "/alerts/generate")
    alert_id = get_alerts(app)[0]["id"]
    employee_id, password = create_user(app, "read-only-alert-user")
    employee = app.test_client()
    login(employee, "read-only-alert-user", password)

    assert employee.get("/alerts").status_code == 200
    assert post_form(employee, "/alerts/generate", follow_redirects=False).status_code == 403
    assert post_form(
        employee, f"/alerts/{alert_id}/acknowledge", follow_redirects=False
    ).status_code == 403


def test_generation_and_state_changes_require_csrf(client):
    assert client.post("/alerts/generate").status_code == 400
    assert client.post("/alerts/1/acknowledge").status_code == 400


def test_generation_skips_unmerged_source_modules_without_failing(client, app):
    add_asset(client)
    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE software_licenses")
        db.execute("DROP TABLE warranties")
        db.execute("DROP TABLE maintenance_schedules")
        db.commit()

    response = post_form(client, "/alerts/generate")
    assert response.status_code == 200
    assert b"software_licenses" in response.data
    assert b"warranties" in response.data
    assert b"maintenance_schedules" in response.data
    assert len(get_alerts(app)) == 1
    assert get_alerts(app)[0]["alert_type"] == "incomplete_record"


def test_alert_history_rejects_update_and_delete(client, app):
    add_asset(client)
    post_form(client, "/alerts/generate")
    alert = get_alerts(app)[0]
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE alert_history SET event_type='tampered' WHERE alert_id=?",
                (alert["id"],),
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "DELETE FROM alert_history WHERE alert_id=?",
                (alert["id"],),
            )
        db.rollback()


def test_alerts_cli_supports_date_override_and_system_actor(app):
    asset_id = None
    with app.app_context():
        cursor = get_db().execute(
            """INSERT INTO assets
               (asset_tag, name, category, manufacturer, model, serial_number,
                location, purchase_date)
               VALUES ('CLI-001', 'CLI asset', 'Laptop', 'Maker', 'Model',
                       'CLI-SER-1', 'Room 2', '2026-01-01')"""
        )
        asset_id = cursor.lastrowid
        get_db().execute(
            """INSERT INTO software_licenses
               (asset_id, product_name, expiry_date, renewal_status)
               VALUES (?, 'CLI test license', '2026-11-21', 'active')""",
            (asset_id,),
        )
        get_db().commit()

    result = app.test_cli_runner().invoke(
        args=["generate-alerts", "--as-of", "2026-11-11"]
    )
    assert result.exit_code == 0, result.output
    assert "Created 1 alert" in result.output
    with app.app_context():
        history = get_db().execute(
            "SELECT actor_username FROM alert_history"
        ).fetchone()
    assert history["actor_username"] == "system"
