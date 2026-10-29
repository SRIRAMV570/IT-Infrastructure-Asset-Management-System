"""S1-02 edit, direct transfer, history, and retirement regression checks."""
import pytest
from app import create_app, get_db


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "s1.sqlite3"),
                       "SECRET_KEY": "test-secret"})


@pytest.fixture()
def client(app):
    return app.test_client()


def add(client, tag="LAP-001", serial="SER-001"):
    return client.post("/assets/new", data={
        "asset_tag": tag, "name": "Laptop", "category": "Computer",
        "manufacturer": "Example", "model": "Model A",
        "serial_number": serial, "location": "Room 1"
    }, follow_redirects=True).request.path


def values(**overrides):
    fields = {"asset_tag": "LAP-001", "name": "Updated laptop",
              "category": "Computer", "manufacturer": "Example",
              "model": "Model B", "serial_number": "SER-001",
              "location": "Room 2", "purchase_date": "2025-01-01"}
    fields.update(overrides)
    return fields


def test_edit_form_updates_persist(client):
    url = add(client)
    assert b"Save changes" in client.get(url + "/edit").data
    result = client.post(url + "/edit", data=values(), follow_redirects=True)
    assert b"Asset updated." in result.data
    assert b"Updated laptop" in result.data
    assert b"Model B" in result.data
    assert b"Room 2" in result.data


def test_edit_rejects_duplicate_tag_and_serial(client):
    add(client)
    url = add(client, "LAP-002", "SER-002")
    for payload in (values(asset_tag="lap-001", serial_number="SER-002"),
                    values(asset_tag="LAP-002", serial_number="ser-001")):
        response = client.post(url + "/edit", data=payload)
        assert response.status_code == 400
        assert b"must be unique" in response.data
    assert b"SER-002" in client.get(url).data


def test_edit_rejects_invalid_data(client):
    url = add(client)
    assert client.post(url + "/edit", data=values(name="")).status_code == 400
    assert client.post(url + "/edit", data=values(purchase_date="invalid")).status_code == 400


def test_transfer_keeps_allocation_history_and_return(client, app):
    url = add(client)
    client.post(url + "/allocate", data={"assignee": "Employee A"})
    result = client.post(url + "/transfer", data={"assignee": "Employee B"}, follow_redirects=True)
    assert b"Asset transferred." in result.data
    assert b"Employee A" in result.data and b"Employee B" in result.data
    with app.app_context():
        rows = get_db().execute("SELECT assignee, returned_at FROM allocations ORDER BY id").fetchall()
        assert len(rows) == 2
        assert rows[0]["assignee"] == "Employee A" and rows[0]["returned_at"] is not None
        assert rows[1]["assignee"] == "Employee B" and rows[1]["returned_at"] is None
    returned = client.post(url + "/return", follow_redirects=True)
    assert b"Asset returned and made available." in returned.data
    assert b"Employee A" in returned.data and b"Employee B" in returned.data


def test_invalid_transfers_never_change_holder(client, app):
    url = add(client)
    assert b"Only allocated assets" in client.post(
        url + "/transfer", data={"assignee": "B"}, follow_redirects=True).data
    client.post(url + "/allocate", data={"assignee": "Employee A"})
    for assignee, expected in [("", b"Enter the new person"),
                               ("A" * 121, b"120 characters"),
                               ("employee a", b"already assigned")]:
        r = client.post(url + "/transfer", data={"assignee": assignee}, follow_redirects=True)
        assert expected in r.data
    with app.app_context():
        rows = get_db().execute("SELECT assignee, returned_at FROM allocations").fetchall()
        assert len(rows) == 1 and rows[0]["assignee"] == "Employee A"
        assert rows[0]["returned_at"] is None


def test_retirement_preserves_history_and_blocks_changes(client, app):
    url = add(client)
    client.post(url + "/allocate", data={"assignee": "A"})
    assert b"Only available assets can be retired" in client.post(
        url + "/retire", follow_redirects=True).data
    client.post(url + "/transfer", data={"assignee": "B"})
    client.post(url + "/return")
    retired = client.post(url + "/retire", follow_redirects=True)
    assert b"Asset retired." in retired.data
    assert b">A<" in retired.data and b">B<" in retired.data
    assert client.get(url + "/edit").status_code == 409
    assert client.post(url + "/edit", data=values()).status_code == 409
    assert b"Only allocated assets" in client.post(
        url + "/transfer", data={"assignee": "C"}, follow_redirects=True).data
    assert b"Only available assets" in client.post(
        url + "/allocate", data={"assignee": "C"}, follow_redirects=True).data
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT status FROM assets").fetchone()["status"] == "retired"
        assert db.execute("SELECT COUNT(*) FROM allocations").fetchone()[0] == 2
