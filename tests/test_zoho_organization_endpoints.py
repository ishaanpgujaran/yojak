from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
import httpx

import app.main as main
import app.services.zoho_organizations as zoho_organizations


TENANT_ID = uuid4()
CONNECTION_ID = uuid4()

WORKOS_TOKEN = "test-workos-access-token"


# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------


@pytest.fixture
def setup_endpoint_mocks(monkeypatch):
    """
    Prepare the dependencies required by the organization
    endpoints.

    The endpoint tests now mock the shared service functions,
    rather than mocking repositories and Zoho API functions
    directly.

    This keeps these tests focused on:
    - HTTP request/response behaviour
    - Authentication dependency behaviour
    - Correct translation of service errors into HTTP errors
    """

    # Mock the shared database connection pool.
    monkeypatch.setattr(
        main.runtime,
        "database_pool",
        object(),
    )

    # Mock the authenticated tenant context.
    async def mock_authenticated_tenant_context():
        return {
            "pool": main.runtime.database_pool,
            "tenant_id": TENANT_ID,
        }

    main.app.dependency_overrides[
        main.get_authenticated_tenant_context
    ] = mock_authenticated_tenant_context

    # Mock the organization discovery service.
    monkeypatch.setattr(
        main,
        "get_zoho_organizations_service",
        AsyncMock(),
    )

    # Mock the organization selection service.
    monkeypatch.setattr(
        main,
        "select_zoho_organization_service",
        AsyncMock(),
    )

    yield

    # Remove the dependency override after each test.
    main.app.dependency_overrides.pop(
        main.get_authenticated_tenant_context,
        None,
    )


@pytest.fixture
async def client():

    transport = httpx.ASGITransport(
        app=main.app,
        raise_app_exceptions=False,
    )

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
# Organization discovery endpoint
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_discover_zero_organizations(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    When Zoho returns no organizations, the endpoint should
    return a successful response indicating that no
    organizations were found.
    """

    main.get_zoho_organizations_service.return_value = {
        "status": "no_organizations_found",
        "selection_required": False,
    }

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "no_organizations_found"
    assert data["selection_required"] is False

    main.get_zoho_organizations_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_discover_single_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    When exactly one organization is available, the service
    should connect it automatically.

    The endpoint should return the connection details.
    """

    main.get_zoho_organizations_service.return_value = {
        "status": "connected",
        "selection_required": False,
        "connection": {
            "id": str(CONNECTION_ID),
            "organization_id": "org-001",
            "organization_name": "ABC Technologies",
        },
    }

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

    main.get_zoho_organizations_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_discover_multiple_organizations(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    When multiple organizations are available, the service
    should return them for the user to select.

    No organization should be automatically selected here.
    """

    main.get_zoho_organizations_service.return_value = {
        "status": "selection_required",
        "selection_required": True,
        "organizations": [
            {
                "organization_id": "org-001",
                "name": "ABC Technologies",
            },
            {
                "organization_id": "org-002",
                "name": "ABC Retail",
            },
        ],
    }

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

    main.get_zoho_organizations_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_discover_organizations_without_authorization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If the tenant has no active Zoho authorization, the
    endpoint should return HTTP 404.
    """

    main.get_zoho_organizations_service.side_effect = (
        zoho_organizations.ZohoActiveAuthorizationNotFoundError()
    )

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]
        == "No active Zoho authorization found. Connect Zoho first."
    )

    main.get_zoho_organizations_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_discover_organizations_handles_discovery_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    A Zoho organization discovery failure should be translated
    into a safe HTTP 500 response.
    """

    main.get_zoho_organizations_service.side_effect = (
        zoho_organizations.ZohoOrganizationDiscoveryError()
    )

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to discover Zoho organizations."
    )


@pytest.mark.anyio
async def test_discover_single_organization_handles_connection_creation_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If automatic connection creation fails for a single
    organization, the endpoint should return HTTP 500.
    """

    main.get_zoho_organizations_service.side_effect = (
        zoho_organizations.ZohoOrganizationConnectionCreationError()
    )

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to create the Zoho organization connection."
    )


@pytest.mark.anyio
async def test_discover_single_organization_handles_activation_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If the connection is created but cannot be activated,
    the endpoint should return HTTP 500.
    """

    main.get_zoho_organizations_service.side_effect = (
        zoho_organizations.ZohoOrganizationActivationError()
    )

    response = await client.get(
        "/oauth/zoho/organizations",
        headers=auth_headers,
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to set the active Zoho organization."
    )


# ---------------------------------------------------------
# POST /oauth/zoho/organizations/select
# Organization selection endpoint
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_select_valid_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    A valid organization selection should return the
    successfully activated connection.
    """

    main.select_zoho_organization_service.return_value = {
        "status": "connected",
        "connection": {
            "id": str(CONNECTION_ID),
            "organization_id": "org-002",
            "organization_name": "ABC Retail",
        },
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

    main.select_zoho_organization_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        "org-002",
    )


@pytest.mark.anyio
async def test_select_inaccessible_organization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    An organization that is not accessible through the
    current Zoho authorization must not be connected.
    """

    main.select_zoho_organization_service.side_effect = (
        zoho_organizations.ZohoOrganizationNotAccessibleError()
    )

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

    main.select_zoho_organization_service.assert_awaited_once_with(
        main.runtime.database_pool,
        TENANT_ID,
        "org-999",
    )


@pytest.mark.anyio
async def test_select_organization_without_authorization(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    Organization selection must fail if the tenant does not
    have an active Zoho authorization.
    """

    main.select_zoho_organization_service.side_effect = (
        zoho_organizations.ZohoActiveAuthorizationNotFoundError()
    )

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 404

    assert (
        response.json()["detail"]
        == "No active Zoho authorization found. Connect Zoho first."
    )


@pytest.mark.anyio
async def test_select_organization_without_selection(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    FastAPI request validation should reject a request that
    does not include the required organization_id field.

    The service must not be called.
    """

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 422

    main.select_zoho_organization_service.assert_not_called()


@pytest.mark.anyio
async def test_select_organization_handles_discovery_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If the service cannot discover the organizations while
    validating the requested selection, return HTTP 500.
    """

    main.select_zoho_organization_service.side_effect = (
        zoho_organizations.ZohoOrganizationDiscoveryError()
    )

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to discover Zoho organizations."
    )


@pytest.mark.anyio
async def test_select_organization_handles_connection_creation_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If the selected organization cannot be saved as a
    merchant connection, return HTTP 500.
    """

    main.select_zoho_organization_service.side_effect = (
        zoho_organizations.ZohoOrganizationConnectionCreationError()
    )

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to create the Zoho organization connection."
    )


@pytest.mark.anyio
async def test_select_organization_handles_activation_failure(
    client,
    auth_headers,
    setup_endpoint_mocks,
):
    """
    If the selected connection cannot be activated,
    return HTTP 500.
    """

    main.select_zoho_organization_service.side_effect = (
        zoho_organizations.ZohoOrganizationActivationError()
    )

    response = await client.post(
        "/oauth/zoho/organizations/select",
        headers=auth_headers,
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 500

    assert (
        response.json()["detail"]
        == "Unable to set the active Zoho organization."
    )


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------


@pytest.mark.anyio
async def test_discover_organizations_without_token(client):
    """
    Requests without a WorkOS bearer token must be rejected.
    """

    response = await client.get(
        "/oauth/zoho/organizations",
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_select_organization_without_token(client):
    """
    Organization selection must also require authentication.
    """

    response = await client.post(
        "/oauth/zoho/organizations/select",
        json={
            "organization_id": "org-001",
        },
    )

    assert response.status_code == 401