from uuid import uuid4
from unittest.mock import AsyncMock

import asyncpg
import pytest

import app.services.zoho_organizations as zoho_organizations


TENANT_ID = uuid4()
AUTHORIZATION_ID = uuid4()
CONNECTION_ID = uuid4()

ORGANIZATION = {
    "organization_id": "org-001",
    "name": "ABC Technologies",
}

ORGANIZATIONS = [
    ORGANIZATION,
    {
        "organization_id": "org-002",
        "name": "ABC Retail",
    },
]


@pytest.fixture
def pool():
    """Provide a placeholder database pool for service tests."""
    return object()


@pytest.fixture
def active_authorization():
    """Represent an active Zoho authorization belonging to the tenant."""
    return {
        "id": AUTHORIZATION_ID,
        "status": "active",
    }


@pytest.fixture
def connection():
    """Represent a merchant connection returned by the repository."""
    return {
        "id": CONNECTION_ID,
        "zoho_organization_id": "org-001",
    }


# =========================================================
# ORGANIZATION DISCOVERY SERVICE
# =========================================================


@pytest.mark.anyio
async def test_discovery_fails_when_active_authorization_is_missing(
    pool,
    monkeypatch,
):
    """Discovery must not proceed without an active authorization."""

    mock_get_authorization = AsyncMock(return_value=None)

    mock_discover = AsyncMock()

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    with pytest.raises(
        zoho_organizations.ZohoActiveAuthorizationNotFoundError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )

    mock_get_authorization.assert_awaited_once_with(
        pool,
        TENANT_ID,
    )

    mock_discover.assert_not_awaited()


@pytest.mark.anyio
async def test_discovery_returns_no_organizations(
    pool,
    active_authorization,
    monkeypatch,
):
    """An empty Zoho organization list should produce a clear result."""

    mock_get_authorization = AsyncMock(
        return_value=active_authorization
    )

    mock_discover = AsyncMock(return_value=[])

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    result = await zoho_organizations.get_zoho_organizations_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "no_organizations_found",
        "selection_required": False,
        "message": "No Zoho organizations were found for this account.",
    }

    mock_discover.assert_awaited_once_with(
        pool,
        TENANT_ID,
        AUTHORIZATION_ID,
    )


@pytest.mark.anyio
async def test_discovery_automatically_connects_single_organization(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """
    When exactly one organization is available, the service
    should create its connection and activate it automatically.
    """

    mock_get_authorization = AsyncMock(
        return_value=active_authorization
    )

    mock_discover = AsyncMock(
        return_value=[ORGANIZATION]
    )

    mock_create_connection = AsyncMock(
        return_value=connection
    )

    mock_activate_connection = AsyncMock(
        return_value=True
    )

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        mock_create_connection,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        mock_activate_connection,
    )

    result = await zoho_organizations.get_zoho_organizations_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "connected",
        "selection_required": False,
        "connection": {
            "id": str(CONNECTION_ID),
            "organization_id": "org-001",
            "organization_name": "ABC Technologies",
        },
    }

    mock_create_connection.assert_awaited_once_with(
        pool,
        TENANT_ID,
        AUTHORIZATION_ID,
        "org-001",
    )

    mock_activate_connection.assert_awaited_once_with(
        pool,
        TENANT_ID,
        CONNECTION_ID,
    )


@pytest.mark.anyio
async def test_discovery_returns_multiple_organizations_for_selection(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    When multiple organizations are available, the service
    should return them without automatically selecting one.
    """

    mock_get_authorization = AsyncMock(
        return_value=active_authorization
    )

    mock_discover = AsyncMock(
        return_value=ORGANIZATIONS
    )

    mock_create_connection = AsyncMock()
    mock_activate_connection = AsyncMock()

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        mock_create_connection,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        mock_activate_connection,
    )

    result = await zoho_organizations.get_zoho_organizations_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "selection_required",
        "selection_required": True,
        "message": (
            "Multiple Zoho organizations were found. "
            "Please select one."
        ),
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

    mock_create_connection.assert_not_awaited()
    mock_activate_connection.assert_not_awaited()


@pytest.mark.anyio
async def test_discovery_wraps_authorization_lookup_failure(
    pool,
    monkeypatch,
):
    """Unexpected repository errors should become service-level errors."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(
            side_effect=RuntimeError("Database operation failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationDiscoveryError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_discovery_wraps_zoho_api_failure(
    pool,
    active_authorization,
    monkeypatch,
):
    """Zoho discovery failures should become service-level errors."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(
            side_effect=RuntimeError("Zoho API failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationDiscoveryError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_discovery_wraps_connection_creation_failure(
    pool,
    active_authorization,
    monkeypatch,
):
    """A failure to create the merchant connection must be explicit."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(
            side_effect=RuntimeError("Connection creation failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationConnectionCreationError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_discovery_wraps_activation_failure(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """A repository exception during activation must be wrapped."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(return_value=connection),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        AsyncMock(
            side_effect=RuntimeError("Activation failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationActivationError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_discovery_fails_when_activation_returns_false(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """A false activation result must not be reported as success."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(return_value=connection),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        AsyncMock(return_value=False),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationActivationError
    ):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


# =========================================================
# ORGANIZATION SELECTION SERVICE
# =========================================================


@pytest.mark.anyio
async def test_selection_fails_when_active_authorization_is_missing(
    pool,
    monkeypatch,
):
    """Selection must require an active Zoho authorization."""

    mock_discover = AsyncMock()

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    with pytest.raises(
        zoho_organizations.ZohoActiveAuthorizationNotFoundError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )

    mock_discover.assert_not_awaited()


@pytest.mark.anyio
async def test_selection_rejects_inaccessible_organization(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    The service must verify that the requested organization
    is actually accessible through this Zoho authorization.
    """

    mock_create_connection = AsyncMock()
    mock_activate_connection = AsyncMock()

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=ORGANIZATIONS),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        mock_create_connection,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        mock_activate_connection,
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationNotAccessibleError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-999",
        )

    mock_create_connection.assert_not_awaited()
    mock_activate_connection.assert_not_awaited()


@pytest.mark.anyio
async def test_selection_connects_accessible_organization(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """A valid organization should be connected and activated."""

    mock_get_authorization = AsyncMock(
        return_value=active_authorization
    )

    mock_discover = AsyncMock(
        return_value=ORGANIZATIONS
    )

    mock_create_connection = AsyncMock(
        return_value=connection
    )

    mock_activate_connection = AsyncMock(
        return_value=True
    )

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        mock_discover,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        mock_create_connection,
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        mock_activate_connection,
    )

    result = await zoho_organizations.select_zoho_organization_service(
        pool,
        TENANT_ID,
        "org-001",
    )

    assert result == {
        "status": "connected",
        "connection": {
            "id": str(CONNECTION_ID),
            "organization_id": "org-001",
            "organization_name": "ABC Technologies",
        },
    }

    mock_create_connection.assert_awaited_once_with(
        pool,
        TENANT_ID,
        AUTHORIZATION_ID,
        "org-001",
    )

    mock_activate_connection.assert_awaited_once_with(
        pool,
        TENANT_ID,
        CONNECTION_ID,
    )


@pytest.mark.anyio
async def test_selection_wraps_discovery_failure(
    pool,
    active_authorization,
    monkeypatch,
):
    """Zoho discovery errors should be translated to a service error."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(
            side_effect=RuntimeError("Zoho API failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationDiscoveryError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )


@pytest.mark.anyio
async def test_selection_wraps_connection_creation_failure(
    pool,
    active_authorization,
    monkeypatch,
):
    """Connection creation errors should be translated."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(
            side_effect=RuntimeError("Connection creation failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationConnectionCreationError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )


@pytest.mark.anyio
async def test_selection_wraps_activation_failure(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """Activation errors should be translated into a service error."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(return_value=connection),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        AsyncMock(
            side_effect=RuntimeError("Activation failed")
        ),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationActivationError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )


@pytest.mark.anyio
async def test_selection_fails_when_activation_returns_false(
    pool,
    active_authorization,
    connection,
    monkeypatch,
):
    """A false activation result must raise an activation error."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "discover_organizations",
        AsyncMock(return_value=[ORGANIZATION]),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "create_merchant_connection",
        AsyncMock(return_value=connection),
    )

    monkeypatch.setattr(
        zoho_organizations,
        "set_active_organization_connection",
        AsyncMock(return_value=False),
    )

    with pytest.raises(
        zoho_organizations.ZohoOrganizationActivationError
    ):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )


# =========================================================
# DATABASE AVAILABILITY ERROR PROPAGATION
# =========================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "database_error",
    [
        asyncpg.PostgresConnectionError("Database unavailable"),
        asyncpg.CannotConnectNowError("Database unavailable"),
        asyncpg.TooManyConnectionsError("Too many connections"),
    ],
)
async def test_discovery_propagates_database_availability_errors(
    pool,
    database_error,
    monkeypatch,
):
    """
    Database availability errors must propagate unchanged.

    They must not be converted into generic organization errors,
    because the API layer has a dedicated HTTP 503 handler.
    """

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(type(database_error)):
        await zoho_organizations.get_zoho_organizations_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "database_error",
    [
        asyncpg.PostgresConnectionError("Database unavailable"),
        asyncpg.CannotConnectNowError("Database unavailable"),
        asyncpg.TooManyConnectionsError("Too many connections"),
    ],
)
async def test_selection_propagates_database_availability_errors(
    pool,
    database_error,
    monkeypatch,
):
    """Selection must preserve database availability exceptions."""

    monkeypatch.setattr(
        zoho_organizations,
        "get_active_zoho_authorization",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(type(database_error)):
        await zoho_organizations.select_zoho_organization_service(
            pool,
            TENANT_ID,
            "org-001",
        )