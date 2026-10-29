import re
import sqlite3

import pytest
from werkzeug.security import check_password_hash

from app import _load_development_secret, create_app


ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "CorrectHorseBatteryStaple42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
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
    response = client.post(
        "/login",
        data={"csrf_token": token, "username": username, "password": password},
        follow_redirects=True,
    )
    return response


def post_form(client, path, data=None, follow_redirects=True):
    values = dict(data or {})
    values["csrf_token"] = csrf_token(client)
    return client.post(path, data=values, follow_redirects=follow_redirects)


def create_user(app, username, role, password="UserPassword42!"):
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", username, "--role", role],
        input=f"{password}\n{password}\n",
    )
    assert result.exit_code == 0, result.output
    return password


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


def test_dashboard_shows_asset_counts(client):
    add_asset(client)
    response = client.get("/")

    assert response.status_code == 200
    assert b"Asset dashboard" in response.data
    assert b"Developer laptop" not in response.data
    assert b">1</strong>" in response.data


def test_asset_creation_requires_tag_name_and_category(client):
    response = post_form(
        client, "/assets/new", {"name": "Laptop"}, follow_redirects=False
    )

    assert response.status_code == 400
    assert b"Asset tag, name, and category are required." in response.data


def test_asset_creation_rejects_duplicate_tag_and_serial(client):
    add_asset(client)

    duplicate_tag = add_asset(client, serial_number="SER-002")
    duplicate_serial = add_asset(client, asset_tag="LAP-002")

    assert b"Asset tag and serial number must be unique." in duplicate_tag.data
    assert b"Asset tag and serial number must be unique." in duplicate_serial.data


def test_invalid_purchase_date_is_rejected(client):
    response = post_form(
        client,
        "/assets/new",
        {
            "asset_tag": "LAP-001",
            "name": "Developer laptop",
            "category": "Laptop",
            "purchase_date": "not-a-date",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert b"Purchase date must be a valid date." in response.data


def test_asset_search_and_status_filter(client):
    add_asset(client)
    second_asset = add_asset(
        client,
        asset_tag="MON-001",
        name="Office monitor",
        category="Monitor",
        serial_number="SER-002",
    )
    post_form(
        client,
        f"{second_asset.request.path}/allocate",
        {"assignee": "Facilities"},
    )

    search_response = client.get("/assets?q=MON-001")
    available_response = client.get("/assets?status=available")
    allocated_response = client.get("/assets?status=allocated")

    assert b"Office monitor" in search_response.data
    assert b"Developer laptop" not in search_response.data
    assert b"Developer laptop" in available_response.data
    assert b"Office monitor" not in available_response.data
    assert b"Office monitor" in allocated_response.data
    assert b"Developer laptop" not in allocated_response.data


def test_allocate_return_preserves_history_and_prevents_double_allocation(client):
    response = add_asset(client)
    asset_url = response.request.path

    allocated = post_form(
        client, f"{asset_url}/allocate", {"assignee": "Alex Morgan"}
    )
    duplicate_allocation = post_form(
        client, f"{asset_url}/allocate", {"assignee": "Finance"}
    )
    returned = post_form(client, f"{asset_url}/return")
    detail_after_return = client.get(asset_url)

    assert b"Asset allocated." in allocated.data
    assert b"Only available assets can be allocated." in duplicate_allocation.data
    assert b"Asset returned and made available." in returned.data
    assert b"Alex Morgan" in detail_after_return.data
    assert b"Current" not in detail_after_return.data


def test_asset_cannot_be_retired_while_allocated(client):
    response = add_asset(client)
    asset_url = response.request.path
    post_form(client, f"{asset_url}/allocate", {"assignee": "IT"})

    retire_response = post_form(client, f"{asset_url}/retire")

    assert b"Only available assets can be retired." in retire_response.data


def test_protected_pages_redirect_anonymous_users_to_login(app):
    anonymous_client = app.test_client()

    response = anonymous_client.get("/assets")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_invalid_login_is_generic_and_does_not_authenticate(app):
    anonymous_client = app.test_client()

    response = login(anonymous_client, ADMIN_USERNAME, "WrongPassword42!")

    assert response.status_code == 200
    assert b"Invalid username or password." in response.data
    assert b"admin" not in response.data.lower().replace(b"it asset management", b"")
    with anonymous_client.session_transaction() as browser_session:
        assert "user_id" not in browser_session


def test_login_uses_salted_password_hash(app):
    connection = sqlite3.connect(app.config["DATABASE"])
    try:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (ADMIN_USERNAME,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] != ADMIN_PASSWORD
    assert check_password_hash(row[0], ADMIN_PASSWORD)
    assert login(app.test_client(), ADMIN_USERNAME, ADMIN_PASSWORD).status_code == 200


def test_employee_can_read_but_cannot_create_or_allocate_assets(app, client):
    password = create_user(app, "employee1", "employee")
    employee = app.test_client()
    assert login(employee, "employee1", password).status_code == 200
    assert add_asset(client).status_code == 200
    asset_url = "/assets/1"

    assert employee.get("/assets").status_code == 200
    assert b"Add asset" not in employee.get("/assets").data
    assert post_form(
        employee,
        "/assets/new",
        {
            "asset_tag": "EMP-002",
            "name": "Unauthorized asset",
            "category": "Laptop",
        },
    ).status_code == 403
    assert post_form(
        employee,
        f"{asset_url}/allocate",
        {"assignee": "Unauthorized"},
    ).status_code == 403


def test_mutating_requests_require_a_valid_csrf_token(client):
    response = client.post(
        "/assets/new",
        data={
            "asset_tag": "LAP-CSRF",
            "name": "CSRF attempt",
            "category": "Laptop",
        },
    )

    assert response.status_code == 400
    assert b"Invalid or missing CSRF token." in response.data


def test_logout_clears_the_authenticated_session(client):
    response = post_form(client, "/logout")

    assert response.status_code == 200
    assert b"You have been signed out." in response.data
    assert client.get("/assets").status_code == 302


@pytest.mark.parametrize("role", ["department_manager", "auditor"])
def test_read_only_roles_cannot_register_assets(app, client, role):
    username = f"{role}1"
    password = create_user(app, username, role)
    read_only_user = app.test_client()
    login(read_only_user, username, password)

    response = post_form(
        read_only_user,
        "/assets/new",
        {
            "asset_tag": f"{role}-001",
            "name": "Read-only attempt",
            "category": "Laptop",
        },
    )

    assert response.status_code == 403


def test_create_admin_is_bootstrap_only(app, tmp_path):
    result = app.test_cli_runner().invoke(
        args=["create-admin", "--username", "anotheradmin"],
        input="AnotherPassword42!\nAnotherPassword42!\n",
    )

    assert result.exit_code != 0
    assert "An account already exists" in result.output


def test_user_creation_requires_admin_and_valid_password(tmp_path):
    empty_app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "empty.sqlite3"),
            "SECRET_KEY": "test-only-secret",
        }
    )
    result = empty_app.test_cli_runner().invoke(
        args=[
            "create-user",
            "--username",
            "employee1",
            "--role",
            "employee",
        ],
        input="UserPassword42!\nUserPassword42!\n",
    )

    assert result.exit_code != 0
    assert "Create the first administrator" in result.output


def test_development_secret_is_stable_between_app_starts(tmp_path):
    first_secret = _load_development_secret(tmp_path)
    second_secret = _load_development_secret(tmp_path)

    assert first_secret == second_secret
    assert len(first_secret) == 64


def test_asset_manager_can_manage_assets(app):
    password = create_user(app, "assetmanager", "asset_manager")
    manager = app.test_client()
    login(manager, "assetmanager", password)

    response = add_asset(manager)

    assert response.status_code == 200
    assert b"Developer laptop" in response.data
