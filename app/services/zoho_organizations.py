from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.repositories import (
    get_active_zoho_authorization,
    create_merchant_connection,
    set_active_organization_connection,
)
from zoho.organizations import discover_organizations


# Exception Classes
class ZohoActiveAuthorizationNotFoundError(Exception):
    """Raised when the tenant has no active Zoho authorization."""


class ZohoOrganizationDiscoveryError(Exception):
    """Raised when organizations cannot be retrieved from Zoho."""


class ZohoOrganizationConnectionCreationError(Exception):
    """Raised when a merchant connection cannot be created."""


class ZohoOrganizationActivationError(Exception):
    """Raised when an organization cannot be activated."""


class ZohoOrganizationNotAccessibleError(Exception):
    """Raised when the selected organization is not accessible."""



# 1 - Zoho Organization Discovery
async def get_zoho_organizations_service(pool, tenant_id):
    """
    Discover organizations accessible through the tenant's active
    Zoho authorization.

    Automatically activates the organization when exactly one is found.
    If multiple organizations are found, returns them for user selection.

    This function contains no HTTP-specific logic. Callers are responsible
    for translating its result and exceptions into their own response format.
    """

    # 1. Retrieve the tenant's active Zoho authorization.
    try:
        zoho_authorization = await get_active_zoho_authorization(
            pool,
            tenant_id,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationDiscoveryError() from error

    if zoho_authorization is None:
        raise ZohoActiveAuthorizationNotFoundError()

    # 2. Discover organizations accessible through this authorization.
    try:
        organizations = await discover_organizations(
            pool,
            tenant_id,
            zoho_authorization["id"],
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationDiscoveryError() from error

    # 3. Handle zero organizations.
    if len(organizations) == 0:
        return {
            "status": "no_organizations_found",
            "selection_required": False,
            "message": "No Zoho organizations were found for this account.",
        }

    # 4. Handle a single organization.
    if len(organizations) == 1:
        organization = organizations[0]

        try:
            connection = await create_merchant_connection(
                pool,
                tenant_id,
                zoho_authorization["id"],
                organization["organization_id"],
            )

        except DATABASE_AVAILABILITY_ERRORS:
            raise

        except Exception as error:
            raise ZohoOrganizationConnectionCreationError() from error

        try:
            is_active = await set_active_organization_connection(
                pool,
                tenant_id,
                connection["id"],
            )

        except DATABASE_AVAILABILITY_ERRORS:
            raise

        except Exception as error:
            raise ZohoOrganizationActivationError() from error

        if not is_active:
            raise ZohoOrganizationActivationError()

        return {
            "status": "connected",
            "selection_required": False,
            "connection": {
                "id": str(connection["id"]),
                "organization_id": connection["zoho_organization_id"],
                "organization_name": organization.get("name"),
            },
        }

    # 5. Handle multiple organizations.
    return {
        "status": "selection_required",
        "selection_required": True,
        "message": "Multiple Zoho organizations were found. Please select one.",
        "organizations": [
            {
                "organization_id": organization["organization_id"],
                "name": organization.get("name"),
            }
            for organization in organizations
        ],
    }


# 2 - Zoho Organization Selection
async def select_zoho_organization_service(
    pool,
    tenant_id,
    organization_id,
):
    """
    Verify that the requested organization is accessible through the
    tenant's active Zoho authorization, then create or retrieve its
    merchant connection and make it active.

    This function contains no HTTP-specific logic. Callers are responsible
    for translating its result and exceptions into their own response format.
    """

    # 1. Retrieve the tenant's active Zoho authorization.
    try:
        zoho_authorization = await get_active_zoho_authorization(
            pool,
            tenant_id,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationDiscoveryError() from error

    if zoho_authorization is None:
        raise ZohoActiveAuthorizationNotFoundError()

    # 2. Discover organizations accessible through this authorization.
    try:
        organizations = await discover_organizations(
            pool,
            tenant_id,
            zoho_authorization["id"],
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationDiscoveryError() from error

    # 3. Verify that the requested organization is accessible.
    selected_organization = next(
        (
            organization
            for organization in organizations
            if organization["organization_id"] == organization_id
        ),
        None,
    )

    if selected_organization is None:
        raise ZohoOrganizationNotAccessibleError()

    # 4. Create or retrieve the merchant connection.
    try:
        connection = await create_merchant_connection(
            pool,
            tenant_id,
            zoho_authorization["id"],
            organization_id,
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationConnectionCreationError() from error

    # 5. Set the selected organization as active.
    try:
        is_active = await set_active_organization_connection(
            pool,
            tenant_id,
            connection["id"],
        )

    except DATABASE_AVAILABILITY_ERRORS:
        raise

    except Exception as error:
        raise ZohoOrganizationActivationError() from error

    if not is_active:
        raise ZohoOrganizationActivationError()

    # 6. Return a service-level result.
    return {
        "status": "connected",
        "connection": {
            "id": str(connection["id"]),
            "organization_id": connection["zoho_organization_id"],
            "organization_name": selected_organization.get("name"),
        },
    }
