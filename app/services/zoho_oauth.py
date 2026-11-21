from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.repositories import (
    create_oauth_state,
    get_zoho_authorization_for_tenant,
    consume_oauth_state,
    create_zoho_authorization,
)
from zoho.auth import (
    build_authorization_url,
    generate_oauth_state,
    get_missing_scopes,
)
from zoho.client import (
    ZohoRefreshTokenError,
    exchange_authorization_code,
)
from zoho.token_manager import get_access_token
from zoho.crypto import encrypt_refresh_token


# Exception Classes
class ZohoAuthorizationLookupError(Exception):
    """Raised when an existing Zoho authorization cannot be retrieved."""


class ZohoAuthorizationValidationError(Exception):
    """Raised when an existing Zoho authorization cannot be validated."""


class ZohoOAuthInitiationError(Exception):
    """Raised when a new Zoho OAuth flow cannot be initiated."""


class ZohoOAuthStateValidationError(Exception):
    """Raised when OAuth state validation fails."""


class ZohoOAuthStateInvalidError(Exception):
    """Raised when OAuth state is invalid, expired, or already used."""


class ZohoAuthorizationDeniedError(Exception):
    """Raised when the user denies Zoho authorization."""


class ZohoAuthorizationCodeMissingError(Exception):
    """Raised when the authorization code is missing."""


class ZohoAuthorizationCodeExchangeError(Exception):
    """Raised when the authorization code cannot be exchanged."""


class ZohoRefreshTokenEncryptionError(Exception):
    """Raised when the refresh token cannot be encrypted."""


class ZohoInvalidScopeFormatError(Exception):
    """Raised when Zoho returns an invalid scope format."""


class ZohoAuthorizationPersistenceError(Exception):
    """Raised when the Zoho authorization cannot be persisted."""


# 1 - Zoho OAuth Initiation
async def connect_zoho_service(pool, tenant_id):
    """
    Reuse a valid Zoho authorization or initiate a new OAuth flow.

    This function contains no HTTP-specific logic. Callers are responsible
    for translating its result and exceptions into their own response format.
    """

    # 1. Retrieve the tenant's existing Zoho authorization.
    try:
        existing_authorization = await get_zoho_authorization_for_tenant(
            pool,
            tenant_id,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoAuthorizationLookupError() from error

    # 2. Check whether an existing active authorization can be reused.
    if (
        existing_authorization is not None
        and existing_authorization["status"] == "active"
    ):
        missing_scopes = get_missing_scopes(
            existing_authorization["granted_scopes"]
        )

        if not missing_scopes:
            try:
                await get_access_token(
                    pool,
                    tenant_id,
                    existing_authorization["id"],
                )

            except ZohoRefreshTokenError as error:
                if error.error_code != "invalid_code":
                    raise ZohoAuthorizationValidationError() from error

                # The token manager has already marked the authorization
                # as revoked. Continue with a fresh OAuth flow.

            except DATABASE_AVAILABILITY_ERRORS:
                raise

            except Exception as error:
                raise ZohoAuthorizationValidationError() from error

            else:
                return {
                    "status": "authorization_reused",
                    "authorization_id": str(existing_authorization["id"]),
                }

    # 3. Initiate a new Zoho OAuth flow.
    try:
        state = generate_oauth_state()

        await create_oauth_state(
            pool,
            state,
            tenant_id,
        )

        authorization_url = build_authorization_url(state)

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOAuthInitiationError() from error

    return {
        "status": "authorization_required",
        "authorization_url": authorization_url,
    }


# 2 - Zoho OAuth Callback
async def handle_zoho_callback_service(pool, code, state, error):
    """
    Validate the OAuth state, exchange the authorization code,
    encrypt the refresh token, and persist the Zoho authorization.

    This function contains no HTTP-specific logic. Callers are responsible
    for translating its result and exceptions into their own response format.
    """

    # 1. Validate and consume OAuth state.
    try:
        tenant_id = await consume_oauth_state(
            pool,
            state,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOAuthStateValidationError() from error

    if tenant_id is None:
        raise ZohoOAuthStateInvalidError()

    # 2. Handle authorization denial.
    if error:
        raise ZohoAuthorizationDeniedError()

    # 3. Validate the authorization code.
    if not code or not code.strip():
        raise ZohoAuthorizationCodeMissingError()

    # 4. Exchange authorization code for tokens.
    try:
        token_data = await exchange_authorization_code(code)

    except Exception as error:
        raise ZohoAuthorizationCodeExchangeError() from error

    # 5. Encrypt the refresh token.
    try:
        refresh_token = token_data.get("refresh_token")

        encrypted_refresh_token = (
            encrypt_refresh_token(refresh_token)
            if isinstance(refresh_token, str) and refresh_token.strip()
            else None
        )

    except Exception as error:
        raise ZohoRefreshTokenEncryptionError() from error

    # 6. Parse granted scopes.
    scopes_value = token_data.get("scope", "")

    if isinstance(scopes_value, str):
        granted_scopes = [
            scope.strip()
            for scope in scopes_value.split(",")
            if scope.strip()
        ]

    elif isinstance(scopes_value, list):
        granted_scopes = scopes_value

    else:
        raise ZohoInvalidScopeFormatError()

    # 7. Persist the authorization.
    try:
        authorization = await create_zoho_authorization(
            pool=pool,
            tenant_id=tenant_id,
            refresh_token_encrypted=encrypted_refresh_token,
            granted_scopes=granted_scopes,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoAuthorizationPersistenceError() from error

    if authorization is None:
        raise ZohoAuthorizationPersistenceError()

    # 8. Return a service-level result.
    return {
        "status": "connected",
        "authorization_id": str(authorization["id"]),
    }


