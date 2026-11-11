import csv
import io
import re
import sqlite3

import pytest

from app import create_app

ADMIN_PASSWORD = "CorrectHorseBatteryStaple42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "reports.sqlite3"),
        "SECRET_KEY": "test-only-secret",
    })
    result = application.test_cli_runner().invoke(
        args=["create-admin", "--username", "admin"],
        input=f"{ADMIN_PASSWORD}\n{ADMIN_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    return application


@pytest.fixture()
def client(app):
    browser = app.test_client()
    token = csrf(browser, "/login")
    browser.post("/login", data={
        "csrf_token": token, "username": "admin", "password": ADMIN_PASSWORD,
    })
    return browser


def csrf(client, path="/"):
    response = client.get(path)
    match = re.search(
        r'name="csrf_token" value="([^"]+)"',
        response.get_data(as_text=True),
    )
    assert match
    return match.group(1)


HEADER = (
    "asset_tag,name,category,manufacturer,model,serial_number,"
    "status,location,purchase_date,assignee\n"
)


def upload(client, content):
    return client.post(
        "/reports/import",
        data={
            "csrf_token": csrf(client),
            "file": (io.BytesIO(content.encode("utf-8")), "assets.csv"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_reports_page_shows_summary_and_import_for_manager(client):
    response = client.get("/reports")
    assert response.status_code == 200
    assert b"Asset reports" in response.data
    assert b"Import assets from CSV" in response.data
    assert b"asset_tag,name,category" in response.data


def test_export_csv_has_expected_headers_and_download_headers(client):
    response = client.get("/reports/assets.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert 'attachment; filename="itams-assets.csv"' == response.headers["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True).lstrip("\ufeff"))))
    assert rows[0] == [
        "asset_tag", "name", "category", "manufacturer", "model",
        "serial_number", "status", "location", "purchase_date",
        "assignee", "created_at",
    ]


def test_import_creates_asset_allocation_and_audit_event(client, app):
    content = HEADER + "LAP-CSV-01,Imported laptop,Laptop,Acme,Book,CSV-001,allocated,Room 1,2026-10-01,Ada Lovelace\n"
    response = upload(client, content)
    assert b"Successfully imported 1 assets." in response.data

    db = sqlite3.connect(app.config["DATABASE"])
    try:
        asset = db.execute(
            "SELECT id, status FROM assets WHERE asset_tag='LAP-CSV-01'"
        ).fetchone()
        allocation = db.execute(
            "SELECT assignee, returned_at FROM allocations WHERE asset_id=?",
            (asset[0],),
        ).fetchone()
        audit = db.execute(
            "SELECT action FROM audit_events WHERE target_id=?",
            (asset[0],),
        ).fetchone()
    finally:
        db.close()
    assert asset[1] == "allocated"
    assert allocation == ("Ada Lovelace", None)
    assert audit == ("asset.imported",)


def test_import_is_atomic_when_a_later_row_is_invalid(client, app):
    content = (
        HEADER
        + "LAP-VALID,Valid laptop,Laptop,Acme,Book,CSV-VALID,available,Room 1,2026-10-01,\n"
        + "LAP-BAD,Bad laptop,Laptop,Acme,Book,CSV-BAD,unknown,Room 1,2026-10-01,\n"
    )
    response = upload(client, content)
    assert b"CSV import rejected" in response.data

    db = sqlite3.connect(app.config["DATABASE"])
    try:
        count = db.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_tag IN ('LAP-VALID','LAP-BAD')"
        ).fetchone()[0]
    finally:
        db.close()
    assert count == 0


def test_import_rejects_duplicate_existing_asset_tag(client):
    upload(client, HEADER + "LAP-DUP,First laptop,Laptop,Acme,Book,SER-DUP,available,Room 1,,\n")
    response = upload(client, HEADER + "LAP-DUP,Second laptop,Laptop,Acme,Book,SER-NEW,available,Room 1,,\n")
    assert b"CSV import rejected" in response.data
    assert b"already exists" in response.data


def test_import_rejects_allocated_asset_without_assignee(client):
    response = upload(
        client,
        HEADER + "LAP-NO-OWNER,Laptop,Laptop,Acme,Book,SER-NO-OWNER,allocated,Room 1,,\n",
    )
    assert b"allocated assets require an assignee" in response.data


def test_import_requires_csrf_token(app):
    browser = app.test_client()
    response = browser.post(
        "/reports/import",
        data={"file": (io.BytesIO((HEADER + "A,B,C,,,,available,,,\n").encode()), "assets.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_employee_cannot_import_assets(app):
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", "employee1", "--role", "employee"],
        input="UserPassword42!\nUserPassword42!\n",
    )
    assert result.exit_code == 0
    browser = app.test_client()
    token = csrf(browser, "/login")
    browser.post("/login", data={
        "csrf_token": token, "username": "employee1", "password": "UserPassword42!",
    })
    response = browser.post(
        "/reports/import",
        data={
            "csrf_token": csrf(browser),
            "file": (io.BytesIO((HEADER + "A,B,C,,,,available,,,\n").encode()), "assets.csv"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 403
