"""S1-03 audit trail behavior and integrity tests."""
import json
import sqlite3
import pytest

from app import get_db
from tests.test_app import add_asset, post_form


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

    actions = [row["action"] for row in audit_rows(app)]
    assert actions == [
        "asset.created", "asset.allocated", "asset.transferred",
        "asset.returned", "asset.retired",
    ]
    assert all(row["actor_username"] == "admin" for row in audit_rows(app))
    assert all(row["target_type"] == "asset" and row["target_id"] == asset_id
               for row in audit_rows(app))
    assert json.loads(audit_rows(app)[2]["details"]) == {
        "from_assignee": "Alice", "to_assignee": "Bob"
    }


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
