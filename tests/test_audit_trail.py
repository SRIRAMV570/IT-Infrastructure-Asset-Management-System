"""S1-03 audit trail behavior and integrity tests."""
import json
import re
import sqlite3

import pytest

from app import create_app, get_db

ADMIN_PASSWORD = "CorrectHorseBatteryStaple42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "audit.sqlite3"),
        "SECRET_KEY": "test-audit-secret",
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
        r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True)
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
    data = dict(values or {})
    data["csrf_token"] = csrf_token(client)
    return client.post(path, data=data, follow_redirects=follow_redirects)


def add_asset(client, **overrides):
    values = {
        "asset_tag": "LAP-001",
        "name": "Developer laptop",
        "category": "Laptop",
        "manufacturer": "Example",
        "model": "Model A",
        "serial_number": "SER-001",
        "location": "Room 12",
    }
    values.update(overrides)
    return post_form(client, "/assets/new", values)


def audit_rows(app):
    with app.app_context():
        return get_db().execute(
            "SELECT actor_id, actor_username, action, target_type, target_id, details "
            "FROM audit_events ORDER BY id"
        ).fetchall()


def test_successful_asset_lifecycle_writes_audit_events(app, client):
    created = add_asset(client)
    asset_id = int(created.request.path.rsplit("/", 1)[-1])
    assert [row["action"] for row in audit_rows(app)] == ["asset.created"]

    post_form(client, f"/assets/{asset_id}/allocate", {"assignee": "Alice"})
    post_form(client, f"/assets/{asset_id}/transfer", {"assignee": "Bob"})
    post_form(client, f"/assets/{asset_id}/return")
    post_form(client, f"/assets/{asset_id}/retire")

    rows = audit_rows(app)
    assert [row["action"] for row in rows] == [
        "asset.created", "asset.allocated", "asset.transferred",
        "asset.returned", "asset.retired",
    ]
    assert all(row["actor_id"] == 1 and row["actor_username"] == "admin"
               for row in rows)
    assert all(row["target_type"] == "asset" and row["target_id"] == asset_id
               for row in rows)
    assert json.loads(rows[2]["details"]) == {
        "from_assignee": "Alice", "to_assignee": "Bob"
    }
    assert json.loads(rows[3]["details"]) == {"assignee": "Bob"}


def test_asset_edit_records_only_changed_fields(app, client):
    created = add_asset(client)
    asset_id = int(created.request.path.rsplit("/", 1)[-1])
    post_form(client, f"/assets/{asset_id}/edit", {
        "asset_tag": "LAP-001", "name": "Renamed laptop",
        "category": "Laptop", "manufacturer": "Example", "model": "Model B",
        "serial_number": "SER-001", "location": "Room 2",
    })
    rows = audit_rows(app)
    assert [row["action"] for row in rows] == ["asset.created", "asset.updated"]
    details = json.loads(rows[-1]["details"])
    assert details["name"] == {"from": "Developer laptop", "to": "Renamed laptop"}
    assert details["location"] == {"from": "Room 12", "to": "Room 2"}


def test_rejected_mutations_do_not_write_audit_events(app, client):
    created = add_asset(client)
    asset_id = int(created.request.path.rsplit("/", 1)[-1])
    post_form(client, f"/assets/{asset_id}/allocate", {"assignee": "Alice"})
    post_form(client, f"/assets/{asset_id}/allocate", {"assignee": "Bob"})
    post_form(client, f"/assets/{asset_id}/transfer", {"assignee": "Alice"})
    actions = [row["action"] for row in audit_rows(app)]
    assert actions == ["asset.created", "asset.allocated"]


def test_audit_events_reject_updates_and_deletes(app, client):
    add_asset(client)
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE audit_events SET action='tampered' WHERE id=1")
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM audit_events WHERE id=1")
        db.rollback()


def test_audit_events_visible_on_asset_detail_and_safe_from_secrets(client):
    created = add_asset(client)
    response = client.get(created.request.path)
    assert b"asset.created" in response.data
    assert b"admin" in response.data
    assert b"password_hash" not in response.data
    assert b"session_token" not in response.data
