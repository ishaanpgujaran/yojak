from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest

import app.services.zoho_oauth as zoho_oauth
from zoho.client import ZohoRefreshTokenError


TENANT_ID = uuid4()
AUTHORIZATION_ID = uuid4()

OAUTH_STATE = "test-oauth-state"
AUTHORIZATION_CODE = "test-authorization-code"
AUTHORIZATION_URL = "https://accounts.zoho.in/oauth/v2/auth?state=test"

GRANTED_SCOPES = [
    "ZohoInventory.items.READ",
    "ZohoInventory.salesorders.READ",
    "ZohoInventory.settings.READ",
]

TOKEN_RESPONSE = {
    "access_token": "test-access-token",
    "refresh_token": "test-refresh-token",
    "scope": ",".join(GRANTED_SCOPES),
}


@pytest.fixture
def pool():
    """Provide a placeholder database pool for service tests."""
    return object()


@pytest.fixture
def active_authorization():
    """Represent an existing active Zoho authorization."""
    return {
        "id": AUTHORIZATION_ID,
        "status": "active",
        "granted_scopes": GRANTED_SCOPES,
    }


@pytest.fixture
def persisted_authorization():
    """Represent an authorization returned after persistence."""
    return {
        "id": AUTHORIZATION_ID,
    }


# =========================================================
# ZOHO OAUTH INITIATION
# connect_zoho_service()
# =========================================================


@pytest.mark.anyio
async def test_connect_initiates_oauth_when_no_authorization_exists(
    pool,
    monkeypatch,
):
    """
    When no previous authorization exists, the service should:
    1. Generate an OAuth state.
    2. Persist the state.
    3. Build the Zoho authorization URL.
    4. Return authorization_required.
    """

    mock_get_authorization = AsyncMock(return_value=None)
    mock_create_state = AsyncMock()

    mock_generate_state = lambda: OAUTH_STATE
    mock_build_url = lambda state: AUTHORIZATION_URL

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "generate_oauth_state",
        mock_generate_state,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        mock_create_state,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "build_authorization_url",
        mock_build_url,
    )

    result = await zoho_oauth.connect_zoho_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "authorization_required",
        "authorization_url": AUTHORIZATION_URL,
    }

    mock_get_authorization.assert_awaited_once_with(
        pool,
        TENANT_ID,
    )

    mock_create_state.assert_awaited_once_with(
        pool,
        OAUTH_STATE,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_connect_reuses_valid_existing_authorization(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    An active authorization with all required scopes and a valid
    refresh token should be reused instead of starting OAuth again.
    """

    mock_get_authorization = AsyncMock(
        return_value=active_authorization
    )

    mock_get_access_token = AsyncMock(
        return_value="valid-access-token"
    )

    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        mock_get_authorization,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_access_token",
        mock_get_access_token,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_missing_scopes",
        lambda scopes: set(),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        mock_create_state,
    )

    result = await zoho_oauth.connect_zoho_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "authorization_reused",
        "authorization_id": str(AUTHORIZATION_ID),
    }

    mock_get_access_token.assert_awaited_once_with(
        pool,
        TENANT_ID,
        AUTHORIZATION_ID,
    )

    mock_create_state.assert_not_awaited()


@pytest.mark.anyio
async def test_connect_starts_oauth_when_required_scopes_are_missing(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    An active authorization without all required scopes
    must not be reused.
    """

    mock_get_access_token = AsyncMock()
    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_missing_scopes",
        lambda scopes: {"ZohoInventory.settings.READ"},
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_access_token",
        mock_get_access_token,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "generate_oauth_state",
        lambda: OAUTH_STATE,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        mock_create_state,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "build_authorization_url",
        lambda state: AUTHORIZATION_URL,
    )

    result = await zoho_oauth.connect_zoho_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "authorization_required",
        "authorization_url": AUTHORIZATION_URL,
    }

    mock_get_access_token.assert_not_awaited()

    mock_create_state.assert_awaited_once_with(
        pool,
        OAUTH_STATE,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_connect_starts_fresh_oauth_when_refresh_token_is_revoked(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    If Zoho reports invalid_code, the token manager marks the
    authorization revoked. The service should then initiate fresh OAuth.
    """

    mock_get_access_token = AsyncMock(
        side_effect=ZohoRefreshTokenError("invalid_code")
    )

    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_missing_scopes",
        lambda scopes: set(),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_access_token",
        mock_get_access_token,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "generate_oauth_state",
        lambda: OAUTH_STATE,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        mock_create_state,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "build_authorization_url",
        lambda state: AUTHORIZATION_URL,
    )

    result = await zoho_oauth.connect_zoho_service(
        pool,
        TENANT_ID,
    )

    assert result == {
        "status": "authorization_required",
        "authorization_url": AUTHORIZATION_URL,
    }

    mock_create_state.assert_awaited_once_with(
        pool,
        OAUTH_STATE,
        TENANT_ID,
    )


@pytest.mark.anyio
async def test_connect_raises_validation_error_for_other_zoho_token_errors(
    pool,
    active_authorization,
    monkeypatch,
):
    """
    Only invalid_code should trigger a fresh OAuth flow.

    Other Zoho refresh-token errors must be reported as
    authorization validation failures.
    """

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_missing_scopes",
        lambda scopes: set(),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_access_token",
        AsyncMock(
            side_effect=ZohoRefreshTokenError(
                "invalid_client_secret"
            )
        ),
    )

    mock_create_state = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        mock_create_state,
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationValidationError
    ):
        await zoho_oauth.connect_zoho_service(
            pool,
            TENANT_ID,
        )

    mock_create_state.assert_not_awaited()


@pytest.mark.anyio
async def test_connect_wraps_unexpected_token_validation_failure(
    pool,
    active_authorization,
    monkeypatch,
):
    """Unexpected token validation failures should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=active_authorization),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_missing_scopes",
        lambda scopes: set(),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "get_access_token",
        AsyncMock(
            side_effect=RuntimeError("Unexpected token failure")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationValidationError
    ):
        await zoho_oauth.connect_zoho_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_connect_wraps_authorization_lookup_failure(
    pool,
    monkeypatch,
):
    """Unexpected authorization lookup errors should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(
            side_effect=RuntimeError("Authorization lookup failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationLookupError
    ):
        await zoho_oauth.connect_zoho_service(
            pool,
            TENANT_ID,
        )


@pytest.mark.anyio
async def test_connect_wraps_oauth_initiation_failure(
    pool,
    monkeypatch,
):
    """Failures while creating the OAuth state should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "generate_oauth_state",
        lambda: OAUTH_STATE,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_oauth_state",
        AsyncMock(
            side_effect=RuntimeError("State persistence failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoOAuthInitiationError
    ):
        await zoho_oauth.connect_zoho_service(
            pool,
            TENANT_ID,
        )


# =========================================================
# ZOHO OAUTH CALLBACK
# handle_zoho_callback_service()
# =========================================================


@pytest.mark.anyio
async def test_callback_completes_successfully(
    pool,
    persisted_authorization,
    monkeypatch,
):
    """
    A valid callback should:
    1. Consume the OAuth state.
    2. Exchange the authorization code.
    3. Encrypt the refresh token.
    4. Parse granted scopes.
    5. Persist the authorization.
    """

    mock_consume_state = AsyncMock(
        return_value=TENANT_ID
    )

    mock_exchange_code = AsyncMock(
        return_value=TOKEN_RESPONSE
    )

    mock_encrypt_token = lambda token: b"encrypted-refresh-token"

    mock_create_authorization = AsyncMock(
        return_value=persisted_authorization
    )

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        mock_consume_state,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        mock_encrypt_token,
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    result = await zoho_oauth.handle_zoho_callback_service(
        pool,
        AUTHORIZATION_CODE,
        OAUTH_STATE,
        None,
    )

    assert result == {
        "status": "connected",
        "authorization_id": str(AUTHORIZATION_ID),
    }

    mock_consume_state.assert_awaited_once_with(
        pool,
        OAUTH_STATE,
    )

    mock_exchange_code.assert_awaited_once_with(
        AUTHORIZATION_CODE,
    )

    mock_create_authorization.assert_awaited_once_with(
        pool=pool,
        tenant_id=TENANT_ID,
        refresh_token_encrypted=b"encrypted-refresh-token",
        granted_scopes=GRANTED_SCOPES,
    )


@pytest.mark.anyio
async def test_callback_rejects_invalid_oauth_state(
    pool,
    monkeypatch,
):
    """An unknown, expired, or already consumed state must be rejected."""

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=None),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    with pytest.raises(
        zoho_oauth.ZohoOAuthStateInvalidError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )

    mock_exchange_code.assert_not_awaited()


@pytest.mark.anyio
async def test_callback_wraps_state_consumption_failure(
    pool,
    monkeypatch,
):
    """Unexpected state repository errors should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(
            side_effect=RuntimeError("State lookup failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoOAuthStateValidationError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )


@pytest.mark.anyio
async def test_callback_handles_user_denial(
    pool,
    monkeypatch,
):
    """A user-denied authorization should produce a specific error."""

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationDeniedError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            None,
            OAUTH_STATE,
            "access_denied",
        )

    mock_exchange_code.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code",
    [
        None,
        "",
        "   ",
    ],
)
async def test_callback_rejects_missing_or_blank_authorization_code(
    pool,
    code,
    monkeypatch,
):
    """A missing or whitespace-only authorization code is invalid."""

    mock_exchange_code = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        mock_exchange_code,
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationCodeMissingError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            code,
            OAUTH_STATE,
            None,
        )

    mock_exchange_code.assert_not_awaited()


@pytest.mark.anyio
async def test_callback_wraps_authorization_code_exchange_failure(
    pool,
    monkeypatch,
):
    """Zoho code-exchange errors should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(
            side_effect=RuntimeError("Zoho token exchange failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationCodeExchangeError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )


@pytest.mark.anyio
async def test_callback_wraps_refresh_token_encryption_failure(
    pool,
    monkeypatch,
):
    """Refresh-token encryption errors should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=TOKEN_RESPONSE),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: (_ for _ in ()).throw(
            ValueError("Encryption failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoRefreshTokenEncryptionError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )


@pytest.mark.anyio
async def test_callback_accepts_scope_string(
    pool,
    persisted_authorization,
    monkeypatch,
):
    """A comma-separated scope string should be parsed correctly."""

    token_response = {
        **TOKEN_RESPONSE,
        "scope": "scope.one,scope.two,scope.three",
    }

    mock_create_authorization = AsyncMock(
        return_value=persisted_authorization
    )

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=token_response),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    result = await zoho_oauth.handle_zoho_callback_service(
        pool,
        AUTHORIZATION_CODE,
        OAUTH_STATE,
        None,
    )

    assert result["status"] == "connected"

    mock_create_authorization.assert_awaited_once_with(
        pool=pool,
        tenant_id=TENANT_ID,
        refresh_token_encrypted=b"encrypted-refresh-token",
        granted_scopes=[
            "scope.one",
            "scope.two",
            "scope.three",
        ],
    )


@pytest.mark.anyio
async def test_callback_accepts_scope_list(
    pool,
    persisted_authorization,
    monkeypatch,
):
    """A list of granted scopes should be preserved."""

    token_response = {
        **TOKEN_RESPONSE,
        "scope": ["scope.one", "scope.two"],
    }

    mock_create_authorization = AsyncMock(
        return_value=persisted_authorization
    )

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=token_response),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    result = await zoho_oauth.handle_zoho_callback_service(
        pool,
        AUTHORIZATION_CODE,
        OAUTH_STATE,
        None,
    )

    assert result["status"] == "connected"

    mock_create_authorization.assert_awaited_once_with(
        pool=pool,
        tenant_id=TENANT_ID,
        refresh_token_encrypted=b"encrypted-refresh-token",
        granted_scopes=["scope.one", "scope.two"],
    )


@pytest.mark.anyio
async def test_callback_rejects_invalid_scope_format(
    pool,
    monkeypatch,
):
    """Scopes must be returned as a string or a list."""

    token_response = {
        **TOKEN_RESPONSE,
        "scope": 123,
    }

    mock_create_authorization = AsyncMock()

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=token_response),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    with pytest.raises(
        zoho_oauth.ZohoInvalidScopeFormatError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )

    mock_create_authorization.assert_not_awaited()


@pytest.mark.anyio
async def test_callback_allows_missing_refresh_token(
    pool,
    persisted_authorization,
    monkeypatch,
):
    """
    The current service permits a missing refresh token and passes
    None to the repository. The repository handles preservation of
    an existing encrypted token during reauthorization.
    """

    token_response = {
        "access_token": "test-access-token",
        "scope": ",".join(GRANTED_SCOPES),
    }

    mock_create_authorization = AsyncMock(
        return_value=persisted_authorization
    )

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=token_response),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        mock_create_authorization,
    )

    result = await zoho_oauth.handle_zoho_callback_service(
        pool,
        AUTHORIZATION_CODE,
        OAUTH_STATE,
        None,
    )

    assert result == {
        "status": "connected",
        "authorization_id": str(AUTHORIZATION_ID),
    }

    mock_create_authorization.assert_awaited_once_with(
        pool=pool,
        tenant_id=TENANT_ID,
        refresh_token_encrypted=None,
        granted_scopes=GRANTED_SCOPES,
    )


@pytest.mark.anyio
async def test_callback_wraps_authorization_persistence_failure(
    pool,
    monkeypatch,
):
    """Unexpected repository errors during persistence should be wrapped."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=TOKEN_RESPONSE),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        AsyncMock(
            side_effect=RuntimeError("Persistence failed")
        ),
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationPersistenceError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )


@pytest.mark.anyio
async def test_callback_rejects_missing_persisted_authorization(
    pool,
    monkeypatch,
):
    """A None repository result must not be reported as success."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=TOKEN_RESPONSE),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        AsyncMock(return_value=None),
    )

    with pytest.raises(
        zoho_oauth.ZohoAuthorizationPersistenceError
    ):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
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
async def test_connect_propagates_database_availability_errors(
    pool,
    database_error,
    monkeypatch,
):
    """
    Database availability failures must propagate unchanged.
    They must not be converted into OAuth service errors.
    """

    monkeypatch.setattr(
        zoho_oauth,
        "get_zoho_authorization_for_tenant",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(type(database_error)):
        await zoho_oauth.connect_zoho_service(
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
async def test_callback_propagates_state_consumption_database_errors(
    pool,
    database_error,
    monkeypatch,
):
    """Database errors during state consumption must propagate."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(type(database_error)):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
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
async def test_callback_propagates_authorization_persistence_database_errors(
    pool,
    database_error,
    monkeypatch,
):
    """Database errors during authorization persistence must propagate."""

    monkeypatch.setattr(
        zoho_oauth,
        "consume_oauth_state",
        AsyncMock(return_value=TENANT_ID),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "exchange_authorization_code",
        AsyncMock(return_value=TOKEN_RESPONSE),
    )

    monkeypatch.setattr(
        zoho_oauth,
        "encrypt_refresh_token",
        lambda token: b"encrypted-refresh-token",
    )

    monkeypatch.setattr(
        zoho_oauth,
        "create_zoho_authorization",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(type(database_error)):
        await zoho_oauth.handle_zoho_callback_service(
            pool,
            AUTHORIZATION_CODE,
            OAUTH_STATE,
            None,
        )