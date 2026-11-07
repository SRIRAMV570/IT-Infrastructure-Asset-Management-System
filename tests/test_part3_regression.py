"""Part-3 regression tests for the implemented ITAMS baseline.

These checks supplement the original Sprint-1 tests. They deliberately do not
pretend that licenses, warranties, alerting, or maintenance are implemented.
"""
import re

import click
import pytest

from app import _load_development_secret, _validate_new_user, create_app, validate_asset


def asset_values(**changes):
    result = {
        "asset_tag": "LAP-101", "name": "Test laptop", "category": "Laptop",
        "manufacturer": "", "model": "", "serial_number": "",
        "location": "Office", "purchase_date": "",
    }
    result.update(changes)
    return result


@pytest.mark.parametrize("field", ["asset_tag", "name", "category"])
def test_tc_01_required_asset_fields_are_validated(field):
    assert "required" in validate_asset(asset_values(**{field: ""}))


@pytest.mark.parametrize("value", ["bad-date", "2026-02-30", "2026/01/01"])
def test_tc_02_invalid_purchase_dates_are_rejected(value):
    assert "valid date" in validate_asset(asset_values(purchase_date=value))


def test_tc_03_valid_optional_purchase_date_is_accepted():
    assert validate_asset(asset_values(purchase_date="2026-10-29")) is None


@pytest.mark.parametrize("username", ["aa", "space name", "bad/name"])
def test_tc_04_usernames_outside_policy_are_rejected(username):
    with pytest.raises(click.ClickException):
        _validate_new_user(username, "LongEnoughPassword42!")


def test_tc_05_short_password_is_rejected():
    with pytest.raises(click.ClickException):
        _validate_new_user("testuser", "short")


def test_tc_06_empty_development_secret_is_rejected(tmp_path):
    (tmp_path / ".flask_secret_key").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty"):
        _load_development_secret(tmp_path)


@pytest.fixture()
def signed_in(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "part3.sqlite3"),
        "SECRET_KEY": "test-only-secret",
    })
    runner = application.test_cli_runner()
    result = runner.invoke(
        args=["create-admin", "--username", "admin"],
        input="CorrectHorseBatteryStaple42!\nCorrectHorseBatteryStaple42!\n",
    )
    assert result.exit_code == 0, result.output
    client = application.test_client()
    token = csrf(client, "/login")
    result = client.post("/login", data={
        "csrf_token": token, "username": "admin",
        "password": "CorrectHorseBatteryStaple42!",
    }, follow_redirects=True)
    assert result.status_code == 200
    return application, client


def csrf(client, path="/"):
    result = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"',
                      result.get_data(as_text=True))
    assert match, "No CSRF field on " + path
    return match.group(1)


def post(client, path, payload=None):
    return client.post(path, data={**(payload or {}), "csrf_token": csrf(client)},
                       follow_redirects=True)


def add_asset(client, tag="LAP-101", location="Office"):
    payload = asset_values(asset_tag=tag, location=location)
    response = post(client, "/assets/new", payload)
    assert response.status_code == 200
    assert b"Asset created." in response.data
    return response.request.path


def test_tc_07_unknown_asset_detail_returns_404(signed_in):
    _, client = signed_in
    assert client.get("/assets/999999").status_code == 404


def test_tc_08_blank_assignee_does_not_allocate_asset(signed_in):
    _, client = signed_in
    url = add_asset(client)
    response = post(client, url + "/allocate", {"assignee": "  "})
    assert b"Enter the person, team, or department" in response.data
    assert b"Available" in client.get(url).data


def test_tc_09_return_without_allocation_is_denied(signed_in):
    _, client = signed_in
    url = add_asset(client)
    response = post(client, url + "/return")
    assert b"Only allocated assets can be returned." in response.data


def test_tc_10_retired_asset_cannot_be_reallocated(signed_in):
    _, client = signed_in
    url = add_asset(client)
    retired = post(client, url + "/retire")
    assert b"Asset retired." in retired.data
    rejected = post(client, url + "/allocate", {"assignee": "Engineer"})
    assert b"Only available assets can be allocated." in rejected.data


def test_tc_11_search_by_location_and_invalid_status_fallback(signed_in):
    _, client = signed_in
    add_asset(client, tag="LAP-101", location="Chennai lab")
    add_asset(client, tag="LAP-102", location="Bengaluru office")
    query = client.get("/assets?q=Chennai")
    assert b"LAP-101" in query.data
    assert b"LAP-102" not in query.data
    fallback = client.get("/assets?status=invalid")
    assert b"LAP-101" in fallback.data
    assert b"LAP-102" in fallback.data


def test_tc_12_invalid_csrf_is_rejected_without_creating_asset(signed_in):
    _, client = signed_in
    response = client.post("/assets/new", data={
        **asset_values(), "csrf_token": "forged-token",
    })
    assert response.status_code == 400
    assert b"Invalid or missing CSRF token" in response.data
    assert b"LAP-101" not in client.get("/assets").data


def test_tc_13_schema_is_safe_to_initialize_twice(tmp_path):
    config = {
        "TESTING": True,
        "DATABASE": str(tmp_path / "same.sqlite3"),
        "SECRET_KEY": "test-only-secret",
    }
    first = create_app(config)
    second = create_app(config)
    assert first.config["DATABASE"] == second.config["DATABASE"]
