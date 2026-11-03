from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
import httpx

import app.main as main


TENANT_ID = uuid4()
AUTHORIZATION_ID = uuid4()
CONNECTION_ID = uuid4()

WORKOS_USER_ID = "test_workos_user_001"

WORKOS_TOKEN = "test-workos-access-token"


@pytest.fixture
def setup_endpoint_mocks(monkeypatch):

    # Mock the database connection pool
    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        object(),
    )

    # Mock WorkOS token verification
    monkeypatch.setattr(
        main.workos_auth.token_verifier,
        "verify_token",
        lambda credentials: SimpleNamespace(
            subject=WORKOS_USER_ID
        ),
    )

    # Mock tenant resolution
    monkeypatch.setattr(
        main,
        "get_or_create_tenant",
        AsyncMock(
            return_value={
                "id": TENANT_ID,
                "workos_user_id": WORKOS_USER_ID,
            }
        ),
    )

    # Mock active Zoho authorization lookup
    monkeypatch.setattr(
        main,
        "get_active_zoho_authorization",
        AsyncMock(
            return_value={
                "id": AUTHORIZATION_ID,
                "tenant_id": TENANT_ID,
                "status": "active",
                "granted_scopes": [
                    "ZohoInventory.items.READ",
                    "ZohoInventory.salesorders.READ",
                ],
            }
        ),
    )

    # Mock organization discovery
    monkeypatch.setattr(
        main,
        "discover_organizations",
        AsyncMock(),
    )

    # Mock merchant connection creation
    monkeypatch.setattr(
        main,
        "create_merchant_connection",
        AsyncMock(
            return_value={
                "id": CONNECTION_ID,
                "tenant_id": TENANT_ID,
                "provider": "zoho_inventory",
                "zoho_organization_id": "org-001",
                "authorization_id": AUTHORIZATION_ID,
                "status": "active",
            }
        ),
    )

    # Mock active organization selection
    monkeypatch.setattr(
        main,
        "set_active_organization_connection",
        AsyncMock(return_value=True),
    )


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=main.app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    return {
        "Authorization": f"Bearer {WORKOS_TOKEN}"
    }


# ---------------------------------------------------------
# GET /oauth/zoho/organizations
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_discover_zero_organizations(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.discover_organizations.return_value = []

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "no_organizations_found"
    assert data["selection_required"] is False

    main.create_merchant_connection.assert_not_called()
    main.set_active_organization_connection.assert_not_called()


@pytest.mark.anyio
async def test_discover_single_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.discover_organizations.return_value = [
        {
            "organization_id": "org-001",
            "name": "ABC Technologies",
        }
    ]

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "connected"
    assert data["selection_required"] is False

    assert data["connection"]["id"] == str(CONNECTION_ID)
    assert data["connection"]["organization_id"] == "org-001"
    assert data["connection"]["organization_name"] == "ABC Technologies"

    main.create_merchant_connection.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        AUTHORIZATION_ID,
        "org-001",
    )

    main.set_active_organization_connection.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        CONNECTION_ID,
    )


@pytest.mark.anyio
async def test_discover_multiple_organizations(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.discover_organizations.return_value = [
        {
            "organization_id": "org-001",
            "name": "ABC Technologies",
        },
        {
            "organization_id": "org-002",
            "name": "ABC Retail",
        },
    ]

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "selection_required"
    assert data["selection_required"] is True

    assert len(data["organizations"]) == 2

    assert data["organizations"][0]["organization_id"] == "org-001"
    assert data["organizations"][0]["name"] == "ABC Technologies"

    assert data["organizations"][1]["organization_id"] == "org-002"
    assert data["organizations"][1]["name"] == "ABC Retail"

    # No connection should be created before user selection
    main.create_merchant_connection.assert_not_called()
    main.set_active_organization_connection.assert_not_called()


# ---------------------------------------------------------
# POST /oauth/zoho/organizations/select
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_select_valid_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.discover_organizations.return_value = [
        {
            "organization_id": "org-001",
            "name": "ABC Technologies",
        },
        {
            "organization_id": "org-002",
            "name": "ABC Retail",
        },
    ]

    main.create_merchant_connection.return_value = {
        "id": CONNECTION_ID,
        "tenant_id": TENANT_ID,
        "provider": "zoho_inventory",
        "zoho_organization_id": "org-002",
        "authorization_id": AUTHORIZATION_ID,
        "status": "active",
    }

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-002",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "connected"

    assert data["connection"]["id"] == str(CONNECTION_ID)
    assert data["connection"]["organization_id"] == "org-002"
    assert data["connection"]["organization_name"] == "ABC Retail"

    main.create_merchant_connection.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        AUTHORIZATION_ID,
        "org-002",
    )

    main.set_active_organization_connection.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        CONNECTION_ID,
    )


@pytest.mark.anyio
async def test_select_inaccessible_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.discover_organizations.return_value = [
        {
            "organization_id": "org-001",
            "name": "ABC Technologies",
        }
    ]

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-999",
        },
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]
        == "The selected organization is not accessible through this Zoho authorization."
    )

    # Unauthorized organization must never be connected
    main.create_merchant_connection.assert_not_called()
    main.set_active_organization_connection.assert_not_called()


@pytest.mark.anyio
async def test_select_organization_without_authorization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    main.get_active_zoho_authorization.return_value = None

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 404

    main.discover_organizations.assert_not_called()
    main.create_merchant_connection.assert_not_called()


@pytest.mark.anyio
async def test_select_organization_without_selection(
    client,
    auth_headers,
    setup_endpoint_mocks,
):

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 422

    main.create_merchant_connection.assert_not_called()


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_discover_organizations_without_token(
    client,
    setup_endpoint_mocks,
):

    response = await client.get(
        "/oauth/zoho/organizations",
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_select_organization_without_token(
    client,
    setup_endpoint_mocks,
):

    response = await client.post(
        "/oauth/zoho/organizations/select",
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 401