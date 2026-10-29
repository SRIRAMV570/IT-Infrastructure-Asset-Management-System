"""S1-02 lifecycle and access-control regression checks."""
import re
import pytest
from app import create_app, get_db

ADMIN_PASSWORD = "CorrectHorseBatteryStaple42!"


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "sprint1.sqlite3"),
        "SECRET_KEY": "test-secret",
    })
    result = application.test_cli_runner().invoke(
        args=["create-admin", "--username", "admin"],
        input=f"{ADMIN_PASSWORD}\n{ADMIN_PASSWORD}\n",
    )
    assert result.exit_code == 0, result.output
    return application


@pytest.fixture()
def client(app):
    c = app.test_client()
    login(c, "admin", ADMIN_PASSWORD)
    return c


def csrf_token(client, path="/"):
    response = client.get(path)
    token = re.search(r'name="csrf_token" value="([^"]+)"',
                      response.get_data(as_text=True))
    assert token is not None, "CSRF token missing from " + path
    return token.group(1)


def login(client, username, password):
    token = csrf_token(client, "/login")
    response = client.post("/login", data={
        "csrf_token": token, "username": username, "password": password,
    }, follow_redirects=True)
    assert response.status_code == 200
    return response


def post(client, url, values=None, follow_redirects=True):
    data = dict(values or {})
    data["csrf_token"] = csrf_token(client)
    return client.post(url, data=data, follow_redirects=follow_redirects)


def add(client, tag="LAP-001", serial="SER-001"):
    result = post(client, "/assets/new", {
        "asset_tag": tag, "name": "Laptop", "category": "Computer",
        "manufacturer": "Example", "model": "Model A",
        "serial_number": serial, "location": "Room 1",
    })
    assert result.status_code == 200, result.data
    return result.request.path


def values(**overrides):
    fields = {
        "asset_tag": "LAP-001", "name": "Updated laptop",
        "category": "Computer", "manufacturer": "Example",
        "model": "Model B", "serial_number": "SER-001",
        "location": "Room 2", "purchase_date": "2025-01-01",
    }
    fields.update(overrides)
    return fields


def test_edit_form_updates_persist(client):
    url = add(client)
    form = client.get(url + "/edit")
    assert b"Save changes" in form.data
    assert b'csrf_token' in form.data
    result = post(client, url + "/edit", values())
    assert b"Asset updated." in result.data
    assert b"Updated laptop" in result.data
    assert b"Model B" in result.data
    assert b"Room 2" in result.data


def test_edit_rejects_duplicate_tag_and_serial(client):
    add(client)
    url = add(client, "LAP-002", "SER-002")
    for payload in (
        values(asset_tag="lap-001", serial_number="SER-002"),
        values(asset_tag="LAP-002", serial_number="ser-001"),
    ):
        response = post(client, url + "/edit", payload, follow_redirects=False)
        assert response.status_code == 400
        assert b"must be unique" in response.data
    assert b"SER-002" in client.get(url).data


def test_edit_rejects_invalid_data(client):
    url = add(client)
    assert post(client, url + "/edit", values(name=""),
                follow_redirects=False).status_code == 400
    assert post(client, url + "/edit", values(purchase_date="invalid"),
                follow_redirects=False).status_code == 400


def test_transfer_keeps_allocation_history_and_return(client, app):
    url = add(client)
    post(client, url + "/allocate", {"assignee": "Employee A"})
    result = post(client, url + "/transfer", {"assignee": "Employee B"})
    assert b"Asset transferred." in result.data
    assert b"Employee A" in result.data and b"Employee B" in result.data
    with app.app_context():
        rows = get_db().execute(
            "SELECT assignee, returned_at FROM allocations ORDER BY id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["assignee"] == "Employee A" and rows[0]["returned_at"] is not None
        assert rows[1]["assignee"] == "Employee B" and rows[1]["returned_at"] is None
    returned = post(client, url + "/return")
    assert b"Asset returned and made available." in returned.data
    assert b"Employee A" in returned.data and b"Employee B" in returned.data


def test_invalid_transfers_never_change_holder(client, app):
    url = add(client)
    assert b"Only allocated assets" in post(
        client, url + "/transfer", {"assignee": "B"}).data
    post(client, url + "/allocate", {"assignee": "Employee A"})
    for assignee, expected in (
        ("", b"Enter the new person"),
        ("A" * 121, b"120 characters"),
        ("employee a", b"already assigned"),
    ):
        result = post(client, url + "/transfer", {"assignee": assignee})
        assert expected in result.data
    with app.app_context():
        rows = get_db().execute(
            "SELECT assignee, returned_at FROM allocations"
        ).fetchall()
        assert len(rows) == 1 and rows[0]["assignee"] == "Employee A"
        assert rows[0]["returned_at"] is None


def test_retirement_preserves_history_and_blocks_changes(client, app):
    url = add(client)
    post(client, url + "/allocate", {"assignee": "A"})
    assert b"Only available assets can be retired" in post(
        client, url + "/retire").data
    post(client, url + "/transfer", {"assignee": "B"})
    post(client, url + "/return")
    retired = post(client, url + "/retire")
    assert b"Asset retired." in retired.data
    assert b">A<" in retired.data and b">B<" in retired.data
    assert client.get(url + "/edit").status_code == 409
    assert post(client, url + "/edit", values(), follow_redirects=False).status_code == 409
    assert b"Only allocated assets" in post(
        client, url + "/transfer", {"assignee": "C"}).data
    assert b"Only available assets" in post(
        client, url + "/allocate", {"assignee": "C"}).data
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT status FROM assets").fetchone()["status"] == "retired"
        assert db.execute("SELECT COUNT(*) FROM allocations").fetchone()[0] == 2


def test_anonymous_users_cannot_access_edit_or_transfer(app, client):
    url = add(client)
    anonymous = app.test_client()
    result = anonymous.get(url + "/edit")
    assert result.status_code == 302 and result.headers["Location"].endswith("/login")
    token = csrf_token(anonymous, "/login")
    result = anonymous.post(url + "/transfer", data={
        "csrf_token": token, "assignee": "Unknown",
    })
    assert result.status_code == 302 and result.headers["Location"].endswith("/login")


def test_read_only_roles_cannot_edit_or_transfer(app, client):
    url = add(client)
    post(client, url + "/allocate", {"assignee": "Employee A"})
    result = app.test_cli_runner().invoke(
        args=["create-user", "--username", "auditor1", "--role", "auditor"],
        input="AuditorPassword42!\nAuditorPassword42!\n",
    )
    assert result.exit_code == 0, result.output
    auditor = app.test_client()
    login(auditor, "auditor1", "AuditorPassword42!")
    assert auditor.get(url + "/edit").status_code == 403
    assert b"Edit asset" not in auditor.get(url).data
    assert b"Transfer asset" not in auditor.get(url).data
    assert post(auditor, url + "/edit", values(), follow_redirects=False).status_code == 403
    assert post(auditor, url + "/transfer", {"assignee": "Auditor"},
                follow_redirects=False).status_code == 403
    assert b"Employee A" in client.get(url).data


def test_edit_and_transfer_require_valid_csrf(client):
    url = add(client)
    post(client, url + "/allocate", {"assignee": "A"})
    assert client.post(url + "/edit", data=values()).status_code == 400
    assert client.post(url + "/transfer", data={"assignee": "B"}).status_code == 400
    with client.application.app_context():
        rows = get_db().execute(
            "SELECT assignee FROM allocations WHERE returned_at IS NULL"
        ).fetchall()
        assert len(rows) == 1 and rows[0]["assignee"] == "A"
