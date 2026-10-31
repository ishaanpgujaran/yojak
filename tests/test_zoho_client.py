from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from zoho.client import (
    exchange_authorization_code,
    refresh_access_token,
    list_organizations,
)


# ==================================================
# 1. Tests for exchanging an authorization code
# ==================================================

@pytest.mark.asyncio
async def test_exchange_authorization_code_success():
    token_data = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
    }

    mock_response = MagicMock()
    mock_response.json.return_value = token_data
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await exchange_authorization_code("test_auth_code")

        assert result == token_data

        mock_client.post.assert_awaited_once()

        args, kwargs = mock_client.post.call_args

        assert args[0].endswith("/oauth/v2/token")
        assert kwargs["params"]["grant_type"] == "authorization_code"
        assert kwargs["params"]["code"] == "test_auth_code"


@pytest.mark.asyncio
async def test_exchange_authorization_code_empty_code():
    with pytest.raises(
        ValueError,
        match="Authorization code cannot be empty",
    ):
        await exchange_authorization_code("")


@pytest.mark.asyncio
async def test_exchange_authorization_code_whitespace_code():
    with pytest.raises(
        ValueError,
        match="Authorization code cannot be empty",
    ):
        await exchange_authorization_code("   ")


@pytest.mark.asyncio
async def test_exchange_authorization_code_missing_access_token():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "refresh_token": "test_refresh_token",
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho response is missing the access token",
        ):
            await exchange_authorization_code("test_auth_code")


@pytest.mark.asyncio
async def test_exchange_authorization_code_missing_refresh_token():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "test_access_token",
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho response is missing the refresh token",
        ):
            await exchange_authorization_code("test_auth_code")


@pytest.mark.asyncio
async def test_exchange_authorization_code_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "error": "invalid_code",
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho rejected the authorization code",
        ):
            await exchange_authorization_code("invalid_auth_code")


@pytest.mark.asyncio
async def test_exchange_authorization_code_invalid_response_format():
    mock_response = MagicMock()
    mock_response.json.return_value = ["unexpected", "response"]
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho returned an invalid token response",
        ):
            await exchange_authorization_code("test_auth_code")


@pytest.mark.asyncio
async def test_exchange_authorization_code_http_error():
    request = httpx.Request(
        "POST",
        "https://accounts.example.com/oauth/v2/token",
    )
    response = httpx.Response(400, request=request)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = (
        httpx.HTTPStatusError(
            "Bad Request",
            request=request,
            response=response,
        )
    )

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(httpx.HTTPStatusError):
            await exchange_authorization_code("test_auth_code")


# ==================================================
# 2. Tests for refreshing an access token
# ==================================================

@pytest.mark.asyncio
async def test_refresh_access_token_success():
    token_data = {
        "access_token": "new_test_access_token",
        "expires_in": 3600,
    }

    mock_response = MagicMock()
    mock_response.json.return_value = token_data
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await refresh_access_token("test_refresh_token")

        assert result == token_data

        mock_client.post.assert_awaited_once()

        args, kwargs = mock_client.post.call_args

        assert kwargs["params"]["grant_type"] == "refresh_token"
        assert kwargs["params"]["refresh_token"] == "test_refresh_token"


@pytest.mark.asyncio
async def test_refresh_access_token_empty_token():
    with pytest.raises(
        ValueError,
        match="Refresh token cannot be empty",
    ):
        await refresh_access_token("")


@pytest.mark.asyncio
async def test_refresh_access_token_whitespace_token():
    with pytest.raises(
        ValueError,
        match="Refresh token cannot be empty",
    ):
        await refresh_access_token("   ")


@pytest.mark.asyncio
async def test_refresh_access_token_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "error": "invalid_code",
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho rejected the refresh token",
        ):
            await refresh_access_token("invalid_refresh_token")


@pytest.mark.asyncio
async def test_refresh_access_token_missing_access_token():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "expires_in": 3600,
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho response is missing the access token",
        ):
            await refresh_access_token("test_refresh_token")


@pytest.mark.asyncio
async def test_refresh_access_token_invalid_response_format():
    mock_response = MagicMock()
    mock_response.json.return_value = ["unexpected", "response"]
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho returned an invalid token response",
        ):
            await refresh_access_token("test_refresh_token")


@pytest.mark.asyncio
async def test_refresh_access_token_http_error():
    request = httpx.Request(
        "POST",
        "https://accounts.example.com/oauth/v2/token",
    )
    response = httpx.Response(401, request=request)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = (
        httpx.HTTPStatusError(
            "Unauthorized",
            request=request,
            response=response,
        )
    )

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(httpx.HTTPStatusError):
            await refresh_access_token("test_refresh_token")


# ==================================================
# 3. Tests for listing Zoho Inventory organizations
# ==================================================

@pytest.mark.asyncio
async def test_list_organizations_success():
    response_data = {
        "code": 0,
        "organizations": [
            {
                "organization_id": "100000001",
                "name": "Organization A",
            },
            {
                "organization_id": "100000002",
                "name": "Organization B",
            },
        ],
    }

    mock_response = MagicMock()
    mock_response.json.return_value = response_data
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await list_organizations("test_access_token")

        assert result == response_data
        assert len(result["organizations"]) == 2

        mock_client.get.assert_awaited_once()

        args, kwargs = mock_client.get.call_args

        assert args[0].endswith("/organizations")
        assert kwargs["headers"]["Authorization"] == (
            "Zoho-oauthtoken test_access_token"
        )


@pytest.mark.asyncio
async def test_list_organizations_empty_access_token():
    with pytest.raises(
        ValueError,
        match="Access token cannot be empty",
    ):
        await list_organizations("")


@pytest.mark.asyncio
async def test_list_organizations_whitespace_access_token():
    with pytest.raises(
        ValueError,
        match="Access token cannot be empty",
    ):
        await list_organizations("   ")


@pytest.mark.asyncio
async def test_list_organizations_api_error():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 1001,
        "message": "Invalid access token",
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho could not retrieve the organizations",
        ):
            await list_organizations("invalid_access_token")


@pytest.mark.asyncio
async def test_list_organizations_missing_organizations_list():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": 0,
    }
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho response is missing the organizations list",
        ):
            await list_organizations("test_access_token")


@pytest.mark.asyncio
async def test_list_organizations_invalid_response_format():
    mock_response = MagicMock()
    mock_response.json.return_value = ["unexpected", "response"]
    mock_response.raise_for_status.return_value = None

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(
            ValueError,
            match="Zoho returned an invalid organization response",
        ):
            await list_organizations("test_access_token")


@pytest.mark.asyncio
async def test_list_organizations_http_error():
    request = httpx.Request(
        "GET",
        "https://inventory.example.com/inventory/v1/organizations",
    )
    response = httpx.Response(401, request=request)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = (
        httpx.HTTPStatusError(
            "Unauthorized",
            request=request,
            response=response,
        )
    )

    with patch("zoho.client.httpx.AsyncClient") as mock_client_class:
        mock_client = (
            mock_client_class.return_value.__aenter__.return_value
        )
        mock_client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(httpx.HTTPStatusError):
            await list_organizations("test_access_token")