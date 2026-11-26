from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

import yojak_mcp.server as mcp_server


WORKOS_USER_ID = "workos-user-test-123"
TENANT_ID = uuid4()

AUTHORIZATION_URL = (
    "https://accounts.zoho.in/oauth/v2/auth?state=test-state"
)


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture
def pool():
    """Provide a placeholder database pool for MCP tool tests."""
    return object()


@pytest.fixture
def tenant():
    """Represent a tenant resolved from an authenticated WorkOS user."""
    return {
        "id": TENANT_ID,
        "workos_user_id": WORKOS_USER_ID,
        "name": "Test Tenant",
    }


@pytest.fixture
def ctx(pool):
    """Provide a minimal MCP context with a database pool."""
    return SimpleNamespace(
        lifespan_context={
            "pool": pool,
        }
    )


@pytest.fixture
def mock_authenticated_user(monkeypatch, pool, tenant):
    """
    Mock WorkOS identity resolution and tenant lookup.

    The actual helper function remains under test. Only its external
    dependencies are mocked.
    """

    mock_get_access_token = lambda: SimpleNamespace(
        subject=WORKOS_USER_ID
    )

    mock_get_or_create_tenant = AsyncMock(
        return_value=tenant
    )

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        mock_get_access_token,
    )

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    return mock_get_or_create_tenant


# =========================================================
# AUTHENTICATED TENANT RESOLUTION
# get_authenticated_tenant()
# =========================================================


@pytest.mark.anyio
async def test_get_authenticated_tenant_resolves_workos_user(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
):
    """
    The authenticated WorkOS subject should be used to resolve
    the corresponding Yojak tenant.
    """

    result = await mcp_server.get_authenticated_tenant(ctx)

    assert result == tenant

    mock_authenticated_user.assert_awaited_once_with(
        pool,
        WORKOS_USER_ID,
    )


@pytest.mark.anyio
async def test_get_authenticated_tenant_rejects_missing_access_token(
    ctx,
    monkeypatch,
):
    """Tenant resolution must fail when no access token is available."""

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        lambda: None,
    )

    mock_get_or_create_tenant = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    with pytest.raises(
        PermissionError,
        match="Authentication is Required",
    ):
        await mcp_server.get_authenticated_tenant(ctx)

    mock_get_or_create_tenant.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "subject",
    [
        None,
        "",
        "   ",
        123,
    ],
)
async def test_get_authenticated_tenant_rejects_invalid_user_identity(
    ctx,
    subject,
    monkeypatch,
):
    """An invalid WorkOS subject must not be used to resolve a tenant."""

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        lambda: SimpleNamespace(subject=subject),
    )

    mock_get_or_create_tenant = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    with pytest.raises(
        PermissionError,
        match="Authenticated user identity is missing",
    ):
        await mcp_server.get_authenticated_tenant(ctx)

    mock_get_or_create_tenant.assert_not_awaited()


@pytest.mark.anyio
async def test_get_authenticated_tenant_rejects_missing_database_pool(
    monkeypatch,
):
    """Tenant resolution must fail when the MCP database pool is missing."""

    ctx = SimpleNamespace(
        lifespan_context={}
    )

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        lambda: SimpleNamespace(subject=WORKOS_USER_ID),
    )

    mock_get_or_create_tenant = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    with pytest.raises(
        RuntimeError,
        match="Database connection pool is unavailable",
    ):
        await mcp_server.get_authenticated_tenant(ctx)

    mock_get_or_create_tenant.assert_not_awaited()


# =========================================================
# MCP TOOL
# yojak_connect_zoho()
# =========================================================


@pytest.mark.anyio
async def test_yojak_connect_zoho_initiates_authorization(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """
    When Zoho authorization is required, the MCP tool should:
    1. Resolve the authenticated tenant.
    2. Call the shared Zoho OAuth service.
    3. Return the authorization URL and next step.
    """

    mock_connect_service = AsyncMock(
        return_value={
            "status": "authorization_required",
            "authorization_url": AUTHORIZATION_URL,
        }
    )

    monkeypatch.setattr(
        mcp_server,
        "connect_zoho_service",
        mock_connect_service,
    )

    result = await mcp_server.yojak_connect_zoho(ctx)

    assert result == {
        "status": "authorization_required",
        "provider": "zoho_inventory",
        "message": (
            "Zoho authorization is required. Open the authorization URL "
            "in a browser and complete the consent process."
        ),
        "authorization_url": AUTHORIZATION_URL,
        "next_step": (
            "Complete Zoho authorization in the browser. "
            "After the callback confirms success, discover your organizations."
        ),
    }

    mock_authenticated_user.assert_awaited_once_with(
        pool,
        WORKOS_USER_ID,
    )

    mock_connect_service.assert_awaited_once_with(
        pool,
        tenant["id"],
    )


@pytest.mark.anyio
async def test_yojak_connect_zoho_reuses_existing_authorization(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """
    When a valid Zoho authorization already exists, the MCP tool
    should report that it can be reused without returning an OAuth URL.
    """

    mock_connect_service = AsyncMock(
        return_value={
            "status": "authorization_reused",
            "authorization_id": "internal-authorization-id",
        }
    )

    monkeypatch.setattr(
        mcp_server,
        "connect_zoho_service",
        mock_connect_service,
    )

    result = await mcp_server.yojak_connect_zoho(ctx)

    assert result == {
        "status": "authorization_reused",
        "provider": "zoho_inventory",
        "message": (
            "An existing valid Zoho authorization was found."
        ),
        "next_step": (
            "Discover the Zoho organizations available to this account."
        ),
    }

    # Internal authorization identifiers should not be exposed to the MCP client.
    assert "authorization_id" not in result
    assert "authorization_url" not in result

    mock_connect_service.assert_awaited_once_with(
        pool,
        tenant["id"],
    )


@pytest.mark.anyio
async def test_yojak_connect_zoho_handles_database_failure_during_tenant_resolution(
    ctx,
    monkeypatch,
):
    """
    Database availability errors during tenant resolution should
    be translated into a safe MCP error.
    """

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        lambda: SimpleNamespace(subject=WORKOS_USER_ID),
    )

    mock_get_or_create_tenant = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Sensitive database connection details"
        )
    )

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    mock_connect_service = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "connect_zoho_service",
        mock_connect_service,
    )

    with pytest.raises(
        RuntimeError,
        match="database is temporarily unavailable",
    ) as error:
        await mcp_server.yojak_connect_zoho(ctx)

    assert "Sensitive database connection details" not in str(error.value)

    mock_connect_service.assert_not_awaited()


@pytest.mark.anyio
async def test_yojak_connect_zoho_handles_database_failure_during_service_call(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Database failures from the Zoho service should be safely translated."""

    mock_connect_service = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Sensitive database connection details"
        )
    )

    monkeypatch.setattr(
        mcp_server,
        "connect_zoho_service",
        mock_connect_service,
    )

    with pytest.raises(
        RuntimeError,
        match="database is temporarily unavailable",
    ) as error:
        await mcp_server.yojak_connect_zoho(ctx)

    assert "Sensitive database connection details" not in str(error.value)

    mock_connect_service.assert_awaited_once_with(
        pool,
        tenant["id"],
    )


# =========================================================
# MCP TOOL - SERVICE ERROR TRANSLATION
# =========================================================


@pytest.mark.anyio
@pytest.mark.parametrize(
    "service_exception, expected_message",
    [
        (
            mcp_server.ZohoAuthorizationLookupError,
            "Unable to retrieve the existing Zoho authorization.",
        ),
        (
            mcp_server.ZohoAuthorizationValidationError,
            "Unable to validate the existing Zoho authorization.",
        ),
        (
            mcp_server.ZohoOAuthInitiationError,
            "Unable to initiate Zoho authorization.",
        ),
    ],
)
async def test_yojak_connect_zoho_translates_service_errors(
    ctx,
    tenant,
    mock_authenticated_user,
    monkeypatch,
    service_exception,
    expected_message,
):
    """
    Known service errors should be translated into clear MCP errors
    instead of exposing internal exception details.
    """

    mock_connect_service = AsyncMock(
        side_effect=service_exception()
    )

    monkeypatch.setattr(
        mcp_server,
        "connect_zoho_service",
        mock_connect_service,
    )

    with pytest.raises(
        RuntimeError,
        match=expected_message,
    ):
        await mcp_server.yojak_connect_zoho(ctx)

    mock_connect_service.assert_awaited_once_with(
        ctx.lifespan_context["pool"],
        tenant["id"],
    )


# =========================================================
# MCP TOOL
# yojak_discover_zoho_organizations()
# =========================================================


@pytest.mark.anyio
async def test_yojak_discover_zoho_organizations_connects_single_org(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """A single discovered organization should be automatically connected."""

    mock_discovery_service = AsyncMock(
        return_value={
            "status": "connected",
            "selection_required": False,
            "connection": {
                "id": "connection-id",
                "organization_id": "zoho-org-123",
                "organization_name": "Test Organization",
            },
        }
    )

    monkeypatch.setattr(
        mcp_server,
        "get_zoho_organizations_service",
        mock_discovery_service,
    )

    result = await mcp_server.yojak_discover_zoho_organizations(ctx)

    assert result["status"] == "connected"
    assert result["connection"]["organization_name"] == "Test Organization"
    assert "ready to use" in result["next_step"]

    mock_authenticated_user.assert_awaited_once_with(
        pool,
        WORKOS_USER_ID,
    )

    mock_discovery_service.assert_awaited_once_with(
        pool,
        tenant["id"],
    )


@pytest.mark.anyio
async def test_yojak_discover_zoho_organizations_returns_multiple_orgs(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Multiple organizations should be returned for user selection."""

    organizations = [
        {
            "organization_id": "zoho-org-123",
            "name": "Mumbai Organization",
        },
        {
            "organization_id": "zoho-org-456",
            "name": "Pune Organization",
        },
    ]

    mock_discovery_service = AsyncMock(
        return_value={
            "status": "selection_required",
            "selection_required": True,
            "message": (
                "Multiple Zoho organizations were found. "
                "Please select one."
            ),
            "organizations": organizations,
        }
    )

    monkeypatch.setattr(
        mcp_server,
        "get_zoho_organizations_service",
        mock_discovery_service,
    )

    result = await mcp_server.yojak_discover_zoho_organizations(ctx)

    assert result["status"] == "selection_required"
    assert result["organizations"] == organizations
    assert "yojak_select_zoho_organization" in result["next_step"]

    mock_discovery_service.assert_awaited_once_with(
        pool,
        tenant["id"],
    )


@pytest.mark.anyio
async def test_yojak_discover_zoho_organizations_handles_missing_authorization(
    ctx,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Discovery should instruct the user to connect Zoho first."""

    mock_discovery_service = AsyncMock(
        side_effect=mcp_server.ZohoActiveAuthorizationNotFoundError()
    )

    monkeypatch.setattr(
        mcp_server,
        "get_zoho_organizations_service",
        mock_discovery_service,
    )

    with pytest.raises(
        RuntimeError,
        match="connect your Zoho account first",
    ):
        await mcp_server.yojak_discover_zoho_organizations(ctx)

    mock_discovery_service.assert_awaited_once_with(
        ctx.lifespan_context["pool"],
        tenant["id"],
    )


@pytest.mark.anyio
async def test_yojak_discover_zoho_organizations_handles_database_failure(
    ctx,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Database errors should be translated without exposing internals."""

    mock_discovery_service = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Sensitive database connection details"
        )
    )

    monkeypatch.setattr(
        mcp_server,
        "get_zoho_organizations_service",
        mock_discovery_service,
    )

    with pytest.raises(
        RuntimeError,
        match="database is temporarily unavailable",
    ) as error:
        await mcp_server.yojak_discover_zoho_organizations(ctx)

    assert "Sensitive database connection details" not in str(error.value)

    mock_discovery_service.assert_awaited_once_with(
        ctx.lifespan_context["pool"],
        tenant["id"],
    )



# =========================================================
# MCP TOOL
# yojak_select_zoho_organization()
# =========================================================


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_activates_selected_org(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """A successfully selected organization should be activated."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        return_value={
            "status": "connected",
            "connection": {
                "id": "connection-id",
                "organization_id": organization_id,
                "organization_name": "Test Organization",
            },
        }
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "connected",
        "connection": {
            "id": "connection-id",
            "organization_id": organization_id,
            "organization_name": "Test Organization",
        },
        "next_step": (
            "You can now use Yojak's Zoho Inventory tools "
            "for this organization."
        ),
    }

    mock_authenticated_user.assert_awaited_once_with(
        pool,
        WORKOS_USER_ID,
    )

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_missing_authorization(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Selection should require an active Zoho authorization."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        side_effect=mcp_server.ZohoActiveAuthorizationNotFoundError()
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "zoho_authorization_required",
        "message": (
            "Connect your Zoho Inventory account before "
            "selecting an organization."
        ),
        "next_step": "Call yojak_connect_zoho.",
    }

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_rejects_inaccessible_org(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """An inaccessible organization must not be activated."""

    organization_id = "inaccessible-org-999"

    mock_selection_service = AsyncMock(
        side_effect=mcp_server.ZohoOrganizationNotAccessibleError()
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "organization_not_accessible",
        "message": (
            "The selected organization is not accessible "
            "through your Zoho account."
        ),
        "next_step": (
            "Call yojak_discover_zoho_organizations to "
            "retrieve accessible organizations."
        ),
    }

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_discovery_failure(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Discovery failures should return a safe structured error."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        side_effect=mcp_server.ZohoOrganizationDiscoveryError()
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "organization_discovery_failed",
        "message": (
            "Yojak could not verify your Zoho organizations. "
            "Please try again later."
        ),
    }

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_connection_creation_failure(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Connection creation failures should return a safe error."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        side_effect=mcp_server.ZohoOrganizationConnectionCreationError()
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "organization_connection_failed",
        "message": (
            "Yojak could not create the organization connection."
        ),
    }

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_activation_failure(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Activation failures should return a safe structured error."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        side_effect=mcp_server.ZohoOrganizationActivationError()
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "organization_activation_failed",
        "message": (
            "Yojak could not activate the selected "
            "organization connection."
        ),
    }

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_database_failure(
    ctx,
    pool,
    tenant,
    mock_authenticated_user,
    monkeypatch,
):
    """Database failures should not expose internal connection details."""

    organization_id = "zoho-org-123"

    mock_selection_service = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Sensitive database connection details"
        )
    )

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        organization_id,
    )

    assert result == {
        "status": "error",
        "error": "database_unavailable",
        "message": (
            "Yojak is temporarily unable to access its database. "
            "Please try again later."
        ),
    }

    assert "Sensitive database connection details" not in str(result)

    mock_selection_service.assert_awaited_once_with(
        pool,
        tenant["id"],
        organization_id,
    )


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_database_failure_during_tenant_resolution(
    ctx,
    monkeypatch,
):
    """Database errors during tenant resolution should return a safe error."""

    mock_get_or_create_tenant = AsyncMock(
        side_effect=asyncpg.PostgresConnectionError(
            "Sensitive database connection details"
        )
    )

    monkeypatch.setattr(
        mcp_server,
        "get_access_token",
        lambda: SimpleNamespace(subject=WORKOS_USER_ID),
    )

    monkeypatch.setattr(
        mcp_server,
        "get_or_create_tenant",
        mock_get_or_create_tenant,
    )

    mock_selection_service = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        "zoho-org-123",
    )

    assert result == {
        "status": "error",
        "error": "database_unavailable",
        "message": (
            "Yojak is temporarily unable to access its database. "
            "Please try again later."
        ),
    }

    assert "Sensitive database connection details" not in str(result)

    mock_selection_service.assert_not_awaited()


@pytest.mark.anyio
async def test_yojak_select_zoho_organization_handles_missing_database_pool(
    tenant,
    monkeypatch,
):
    """A missing database pool should return a safe error."""

    ctx = SimpleNamespace(
        lifespan_context={}
    )

    mock_get_authenticated_tenant = AsyncMock(
        return_value=tenant
    )

    monkeypatch.setattr(
        mcp_server,
        "get_authenticated_tenant",
        mock_get_authenticated_tenant,
    )

    mock_selection_service = AsyncMock()

    monkeypatch.setattr(
        mcp_server,
        "select_zoho_organization_service",
        mock_selection_service,
    )

    result = await mcp_server.yojak_select_zoho_organization(
        ctx,
        "zoho-org-123",
    )

    assert result == {
        "status": "error",
        "error": "database_unavailable",
        "message": "Yojak's database connection is not available.",
    }

    mock_get_authenticated_tenant.assert_awaited_once_with(ctx)
    mock_selection_service.assert_not_awaited()



