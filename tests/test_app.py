import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "test.sqlite3"),
            "SECRET_KEY": "test-only-secret",
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()


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
    return client.post("/assets/new", data=values, follow_redirects=True)


def test_dashboard_shows_asset_counts(client):
    add_asset(client)
    response = client.get("/")

    assert response.status_code == 200
    assert b"Asset dashboard" in response.data
    assert b"Developer laptop" not in response.data
    assert b">1</strong>" in response.data


def test_asset_creation_requires_tag_name_and_category(client):
    response = client.post("/assets/new", data={"name": "Laptop"})

    assert response.status_code == 400
    assert b"Asset tag, name, and category are required." in response.data


def test_asset_creation_rejects_duplicate_tag_and_serial(client):
    add_asset(client)

    duplicate_tag = add_asset(client, serial_number="SER-002")
    duplicate_serial = add_asset(client, asset_tag="LAP-002")

    assert b"Asset tag and serial number must be unique." in duplicate_tag.data
    assert b"Asset tag and serial number must be unique." in duplicate_serial.data


def test_invalid_purchase_date_is_rejected(client):
    response = client.post(
        "/assets/new",
        data={
            "asset_tag": "LAP-001",
            "name": "Developer laptop",
            "category": "Laptop",
            "purchase_date": "not-a-date",
        },
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
    client.post(
        f"{second_asset.request.path}/allocate",
        data={"assignee": "Facilities"},
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
    allocate_url = f"{asset_url}/allocate"
    return_url = f"{asset_url}/return"

    allocated = client.post(
        allocate_url, data={"assignee": "Alex Morgan"}, follow_redirects=True
    )
    duplicate_allocation = client.post(
        allocate_url, data={"assignee": "Finance"}, follow_redirects=True
    )
    returned = client.post(return_url, follow_redirects=True)
    detail_after_return = client.get(asset_url)

    assert b"Asset allocated." in allocated.data
    assert b"Only available assets can be allocated." in duplicate_allocation.data
    assert b"Asset returned and made available." in returned.data
    assert b"Alex Morgan" in detail_after_return.data
    assert b"Current" not in detail_after_return.data


def test_asset_cannot_be_retired_while_allocated(client):
    response = add_asset(client)
    asset_url = response.request.path
    client.post(f"{asset_url}/allocate", data={"assignee": "IT"})

    retire_response = client.post(
        f"{asset_url}/retire", follow_redirects=True
    )

    assert b"Only available assets can be retired." in retire_response.data
