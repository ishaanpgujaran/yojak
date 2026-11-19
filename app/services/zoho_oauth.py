from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.repositories import (
    create_oauth_state,
    get_zoho_authorization_for_tenant,
)
from zoho.auth import (
    build_authorization_url,
    generate_oauth_state,
    get_missing_scopes,
)
from zoho.client import ZohoRefreshTokenError
from zoho.token_manager import get_access_token


class ZohoAuthorizationLookupError(Exception):
    """Raised when an existing Zoho authorization cannot be retrieved."""


class ZohoAuthorizationValidationError(Exception):
    """Raised when an existing Zoho authorization cannot be validated."""


class ZohoOAuthInitiationError(Exception):
    """Raised when a new Zoho OAuth flow cannot be initiated."""


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