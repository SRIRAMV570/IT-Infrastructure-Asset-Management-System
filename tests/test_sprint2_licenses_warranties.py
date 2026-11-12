"""S2-01 license/warranty and S2-05 security/quality regression tests."""
import re
import sqlite3

import pytest

from app import create_app, get_db
from scripts.sqlite_backup import backup_database, restore_database, verify_database

PASSWORD = "CorrectHorseBatteryStaple42!"

@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "s2.sqlite3"),
        "SECRET_KEY": "s2-test-secret",
    })
    result = application.test_cli_runner().invoke(
        args=["create-admin", "--username", "admin"],
        input=f"{PASSWORD}\n{PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    return application

@pytest.fixture()
def client(app):
    c = app.test_client()
    token = csrf(c, "/login")
    response = c.post("/login", data={
        "csrf_token": token, "username": "admin", "password": PASSWORD,
    }, follow_redirects=True)
    assert response.status_code == 200
    return c

def csrf(client, path="/"):
    response = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match
    return match.group(1)

def post(client, path, values=None, follow=True):
    data = dict(values or {})
    data["csrf_token"] = csrf(client)
    return client.post(path, data=data, follow_redirects=follow)

def add_asset(client):
    response = post(client, "/assets/new", {
        "asset_tag": "S2-LAP-001", "name": "S2 Test Laptop",
        "category": "Laptop", "serial_number": "S2-SERIAL-001",
    })
    assert response.status_code == 200
    return int(response.request.path.rsplit("/", 1)[-1])

def license_payload(**overrides):
    values = {
        "product_name": "Design Suite", "vendor": "Example Vendor",
        "license_reference": "PO-REF-2048", "entitlement_count": "10",
        "used_count": "12", "expiry_date": "2099-12-31",
        "renewal_status": "renewal_pending", "notes": "Synthetic test record",
    }
    values.update(overrides)
    return values

def warranty_payload(asset_id, **overrides):
    values = {
        "asset_id": str(asset_id), "provider": "Example OEM",
        "warranty_reference": "WARRANTY-REF-1", "start_date": "2026-01-01",
        "end_date": "2027-01-01", "notes": "Synthetic coverage",
    }
    values.update(overrides)
    return values

def test_license_create_flags_over_entitlement_and_lists_record(client):
    response = post(client, "/licenses/new", license_payload())
    assert response.status_code == 200
    page = client.get("/licenses")
    assert b"Design Suite" in page.data
    assert b"Over entitlement" in page.data
    assert b"renewal pending" in page.data.lower()

def test_license_can_link_to_asset_and_edit_usage(client):
    asset_id = add_asset(client)
    response = post(client, "/licenses/new", license_payload(asset_id=str(asset_id)))
    assert response.status_code == 200
    with client.application.app_context():
        license_id = get_db().execute("SELECT id FROM software_licenses").fetchone()["id"]
    updated = post(client, f"/licenses/{license_id}/edit",
                   license_payload(asset_id=str(asset_id), used_count="8", renewal_status="renewed"))
    assert updated.status_code == 200
    assert b"Within entitlement" in client.get("/licenses").data
    with client.application.app_context():
        row = get_db().execute("SELECT used_count, renewal_status FROM software_licenses").fetchone()
        assert row["used_count"] == 8 and row["renewal_status"] == "renewed"

@pytest.mark.parametrize("changes", [
    {"entitlement_count": "0"}, {"used_count": "-1"},
    {"entitlement_count": "one"}, {"expiry_date": "31-12-2099"},
    {"renewal_status": "arbitrary"},
])
def test_invalid_license_values_are_rejected_without_persistence(client, changes):
    response = post(client, "/licenses/new", license_payload(**changes), follow=False)
    assert response.status_code == 400
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM software_licenses").fetchone()[0] == 0

def test_license_audit_does_not_store_sensitive_activation_keys(client):
    response = post(client, "/licenses/new", license_payload())
    assert response.status_code == 200
    with client.application.app_context():
        event = get_db().execute(
            "SELECT action, details FROM audit_events WHERE target_type='license'"
        ).fetchone()
        columns = {row["name"] for row in get_db().execute("PRAGMA table_info(software_licenses)")}
    assert event["action"] == "license.created"
    assert "activation_key" not in columns and "password" not in columns
    assert "activation_key" not in event["details"].lower()
    assert "license_reference" not in event["details"]

def test_warranty_create_links_to_asset_and_appears_in_both_views(client):
    asset_id = add_asset(client)
    response = post(client, "/warranties/new", warranty_payload(asset_id))
    assert response.status_code == 200
    assert b"Example OEM" in client.get("/warranties").data
    assert b"Example OEM" in client.get(f"/assets/{asset_id}").data

def test_warranty_rejects_invalid_or_reversed_coverage_dates(client):
    asset_id = add_asset(client)
    for changes in ({"start_date": "bad-date"}, {"end_date": "2025-01-01"}):
        response = post(client, "/warranties/new", warranty_payload(asset_id, **changes), follow=False)
        assert response.status_code == 400
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM warranties").fetchone()[0] == 0

def test_non_manager_cannot_create_license_or_warranty(app):
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", "employee1", "--role", "employee"],
        input="EmployeePassword42!\nEmployeePassword42!\n",
    )
    assert result.exit_code == 0
    c = app.test_client()
    c.post("/login", data={"csrf_token": csrf(c, "/login"),
        "username": "employee1", "password": "EmployeePassword42!"})
    assert c.get("/licenses/new").status_code == 403
    assert c.get("/warranties/new").status_code == 403

def test_license_and_warranty_mutations_require_csrf(client):
    assert client.post("/licenses/new", data=license_payload()).status_code == 400
    assert client.post("/warranties/new", data=warranty_payload(add_asset(client))).status_code == 400

def test_sql_injection_like_search_and_license_text_remain_data(client):
    payload = license_payload(product_name="'; DROP TABLE assets;--")
    assert post(client, "/licenses/new", payload).status_code == 200
    assert client.get("/assets?q=%27%3B%20DROP%20TABLE%20assets%3B--").status_code == 200
    with client.application.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
        assert get_db().execute("SELECT COUNT(*) FROM software_licenses").fetchone()[0] == 1

def test_sqlite_backup_restore_integrity_round_trip(app, tmp_path):
    source = app.config["DATABASE"]
    backup = tmp_path / "s2-backup.sqlite3"
    restored = tmp_path / "s2-restored.sqlite3"
    backup_database(source, backup)
    assert verify_database(backup) == "ok"
    restore_database(backup, restored)
    assert verify_database(restored) == "ok"
    with sqlite3.connect(restored) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
