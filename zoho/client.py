from typing import Any
import httpx
from app.config import settings

# 1. Exchanging Authorization Code or Tokens
async def exchange_authorization_code(
        code: str,
    ) -> dict[str, Any]:

    """Exchange a Zoho OAuth Authorization Code for Tokens."""

    if not code or not code.strip():
        raise ValueError("Authorization code cannot be empty.")

    token_url = (f"{settings.zoho_accounts_url.rstrip('/')}/oauth/v2/token")

    params = {
        "grant_type": "authorization_code",
        "client_id": settings.zoho_client_id,
        "client_secret": settings.zoho_client_secret,
        "redirect_uri": settings.zoho_redirect_uri,
        "code": code,
    }

    async with httpx.AsyncClient(timeout = 15.0) as client:
        response = await client.post(
            token_url,
            params = params,
        )

    response.raise_for_status()

    token_data = response.json()

    if not isinstance(token_data, dict):
        raise ValueError("Zoho returned an invalid token response.")
    
    if token_data.get("error"):
        raise ValueError("Zoho rejected the authorization code.")

    if not token_data.get("access_token"):
        raise ValueError("Zoho response is missing the access token.")
    
    if not token_data.get("refresh_token"):
        raise ValueError("Zoho response is missing the refresh token.")
    
    return token_data


# 2. Get new Access Token using Refresh Token
async def refresh_access_token(
        refresh_token: str,
    ) -> dict[str, Any]:

    """Obtain a new Zoho Access Token using a Refresh Token"""

    if not refresh_token or not refresh_token.strip():
        raise ValueError("Refresh token cannot be empty.")
    
    token_url = (f"{settings.zoho_accounts_url.rstrip('/')}/oauth/v2/token")

    params = {
        "grant_type": "refresh_token",
        "client_id": settings.zoho_client_id,
        "client_secret": settings.zoho_client_secret,
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient(timeout = 15.0) as client:
        response = await client.post(
            token_url,
            params = params,
        )

    response.raise_for_status()

    token_data = response.json()

    if not isinstance(token_data, dict):
        raise ValueError("Zoho returned an invalid token response.")
    
    if token_data.get("error"):
        raise ValueError("Zoho rejected the refresh token.")
    
    if not token_data.get("access_token"):
        raise ValueError("Zoho response is missing the access token.")

    return token_data


# 3. List Zoho Inventory Organizations
async def list_organizations(
        access_token: str,
    ) -> dict[str, Any]:

    """List Zoho Inventory Organizations accessible to the user."""

    if not access_token or not access_token.strip():
        raise ValueError("Access token cannot be empty.")
    
    organizations_url = (f"{settings.zoho_api_base_url.rstrip('/')}/organizations")

    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    async with httpx.AsyncClient(timeout = 15.0) as client:
        response = await client.get(
            organizations_url,
            headers = headers,
        )

    response.raise_for_status()

    response_data = response.json()

    if not isinstance(response_data, dict):
        raise ValueError("Zoho returned an invalid organization response.")
    
    if response_data.get("code") != 0:
        raise ValueError("Zoho could not retrieve the organizations.")
    
    organizations = response_data.get("organizations")

    if not isinstance(organizations, list):
        raise ValueError("Zoho response is missing the organizations list.")
    
    return response_data
    
    

