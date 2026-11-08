import pytest
import time

from uuid import uuid4

from unittest.mock import AsyncMock, patch, ANY

import asyncio

from zoho.client import ZohoRefreshTokenError

from zoho.token_manager import (
    cache_access_token,
    get_cached_access_token,
    _token_cache,
    get_access_token,
    get_token_lock,
)


@pytest.fixture
def cache_key():
    return (uuid4(), uuid4())


def test_cache_access_token(cache_key):
    token_data = {
        "access_token": "test_access_token",
        "expires_in": 3600,
    }

    cache_access_token(cache_key, token_data)

    cached_token = _token_cache[cache_key]

    assert cached_token["access_token"] == "test_access_token"
    assert cached_token["expires_at"] > time.monotonic()


def test_get_cached_access_token(cache_key):
    token_data = {
        "access_token": "test_access_token",
        "expires_in": 3600,
    }

    cache_access_token(cache_key, token_data)

    result = get_cached_access_token(cache_key)

    assert result == "test_access_token"

def test_get_cached_access_token_expired(cache_key):
    token_data = {
        "access_token": "expired_access_token",
        "expires_in": 3600,
    }

    cache_access_token(cache_key, token_data)

    # Simulate a token that expires in 30 seconds
    _token_cache[cache_key]["expires_at"] = time.monotonic() + 30

    result = get_cached_access_token(cache_key)

    assert result is None
    assert cache_key not in _token_cache


@pytest.mark.anyio
async def test_get_access_token_cache_miss(cache_key):

    tenant_id, authorization_id = cache_key

    encrypted_refresh_token = b"encrypted_refresh_token"

    token_data = {
        "access_token": "new_access_token",
        "expires_in": 3600,
    }

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
        ) as mock_get_refresh_token,
        patch(
            "zoho.token_manager.decrypt_refresh_token",
        ) as mock_decrypt,
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh,
    ):

        mock_get_refresh_token.return_value = encrypted_refresh_token
        mock_decrypt.return_value = "actual_refresh_token"
        mock_refresh.return_value = token_data

        result = await get_access_token(
            pool=AsyncMock(),
            tenant_id=tenant_id,
            authorization_id=authorization_id,
        )

        assert result == "new_access_token"

        mock_get_refresh_token.assert_awaited_once()
        mock_decrypt.assert_called_once_with(encrypted_refresh_token)
        mock_refresh.assert_awaited_once_with("actual_refresh_token")

        assert get_cached_access_token(cache_key) == "new_access_token"


@pytest.mark.anyio
async def test_get_access_token_cache_hit(cache_key):

    tenant_id, authorization_id = cache_key

    # Populate the cache first
    cache_access_token(
        cache_key,
        {
            "access_token": "cached_access_token",
            "expires_in": 3600,
        },
    )

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
        ) as mock_get_refresh_token,
        patch(
            "zoho.token_manager.decrypt_refresh_token",
        ) as mock_decrypt,
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh,
    ):

        result = await get_access_token(
            pool=AsyncMock(),
            tenant_id=tenant_id,
            authorization_id=authorization_id,
        )

        assert result == "cached_access_token"

        mock_get_refresh_token.assert_not_awaited()
        mock_decrypt.assert_not_called()
        mock_refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_get_access_token_missing_authorization(cache_key):

    tenant_id, authorization_id = cache_key

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
        ) as mock_get_refresh_token,
        patch(
            "zoho.token_manager.decrypt_refresh_token",
        ) as mock_decrypt,
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh,
    ):

        mock_get_refresh_token.return_value = None

        with pytest.raises(
            ValueError,
            match="No active Zoho authorization found",
        ):
            await get_access_token(
                pool=AsyncMock(),
                tenant_id=tenant_id,
                authorization_id=authorization_id,
            )

        mock_get_refresh_token.assert_awaited_once()
        mock_decrypt.assert_not_called()
        mock_refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_get_access_token_refresh_failure(cache_key):

    tenant_id, authorization_id = cache_key

    encrypted_refresh_token = b"encrypted_refresh_token"

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
        ) as mock_get_refresh_token,
        patch(
            "zoho.token_manager.decrypt_refresh_token",
        ) as mock_decrypt,
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh,
    ):

        mock_get_refresh_token.return_value = encrypted_refresh_token
        mock_decrypt.return_value = "actual_refresh_token"

        mock_refresh.side_effect = ValueError(
            "Zoho rejected the refresh token."
        )

        with pytest.raises(
            ValueError,
            match="Zoho rejected the refresh token",
        ):
            await get_access_token(
                pool=AsyncMock(),
                tenant_id=tenant_id,
                authorization_id=authorization_id,
            )

        mock_get_refresh_token.assert_awaited_once()
        mock_decrypt.assert_called_once_with(encrypted_refresh_token)
        mock_refresh.assert_awaited_once_with("actual_refresh_token")

        assert cache_key not in _token_cache


@pytest.mark.anyio
async def test_concurrent_requests_refresh_token_once(cache_key):

    tenant_id, connection_id = cache_key

    encrypted_refresh_token = b"encrypted_refresh_token"

    token_data = {
        "access_token": "shared_access_token",
        "expires_in": 3600,
    }

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
        ) as mock_get_refresh_token,
        patch(
            "zoho.token_manager.decrypt_refresh_token",
        ) as mock_decrypt,
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
        ) as mock_refresh,
    ):

        mock_get_refresh_token.return_value = encrypted_refresh_token
        mock_decrypt.return_value = "actual_refresh_token"

        async def delayed_refresh(refresh_token):
            await asyncio.sleep(0.1)
            return token_data

        mock_refresh.side_effect = delayed_refresh

        results = await asyncio.gather(
            get_access_token(AsyncMock(), tenant_id, connection_id),
            get_access_token(AsyncMock(), tenant_id, connection_id),
            get_access_token(AsyncMock(), tenant_id, connection_id),
        )

        assert results == [
            "shared_access_token",
            "shared_access_token",
            "shared_access_token",
        ]

        mock_get_refresh_token.assert_awaited_once()
        mock_decrypt.assert_called_once_with(encrypted_refresh_token)
        mock_refresh.assert_awaited_once_with("actual_refresh_token")


@pytest.mark.anyio
async def test_lock_released_after_refresh_failure(cache_key):

    tenant_id, connection_id = cache_key

    lock = get_token_lock(cache_key)

    with patch(
        "zoho.token_manager.get_zoho_refresh_token_for_authorization",
        new_callable=AsyncMock,
    ) as mock_get_refresh_token:

        mock_get_refresh_token.return_value = b"encrypted_refresh_token"

        with (
            patch(
                "zoho.token_manager.decrypt_refresh_token",
                return_value="actual_refresh_token",
            ),
            patch(
                "zoho.token_manager.refresh_access_token",
                new_callable=AsyncMock,
                side_effect=ValueError("Refresh failed"),
            ),
        ):

            with pytest.raises(ValueError, match="Refresh failed"):
                await get_access_token(
                    AsyncMock(),
                    tenant_id,
                    connection_id,
                )

    assert not lock.locked()


# Invalid refresh token revokes authorization
@pytest.mark.anyio
async def test_get_access_token_revoked_refresh_token(cache_key):

    tenant_id, authorization_id = cache_key

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
            return_value=b"encrypted_refresh_token",
        ),
        patch(
            "zoho.token_manager.decrypt_refresh_token",
            return_value="actual_refresh_token",
        ),
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
            side_effect=ZohoRefreshTokenError("invalid_code"),
        ),
        patch(
            "zoho.token_manager.update_zoho_authorization_status",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_update_status,
    ):

        with pytest.raises(
            ZohoRefreshTokenError,
            match="invalid_code",
        ):
            await get_access_token(
                AsyncMock(),
                tenant_id,
                authorization_id,
            )

        mock_update_status.assert_awaited_once_with(
            ANY,
            tenant_id,
            authorization_id,
            "revoked",
        )

    assert cache_key not in _token_cache


# Invalid client credentials do not revoke authorization
@pytest.mark.anyio
async def test_get_access_token_invalid_client_does_not_revoke(cache_key):

    tenant_id, authorization_id = cache_key

    with (
        patch(
            "zoho.token_manager.get_zoho_refresh_token_for_authorization",
            new_callable=AsyncMock,
            return_value=b"encrypted_refresh_token",
        ),
        patch(
            "zoho.token_manager.decrypt_refresh_token",
            return_value="actual_refresh_token",
        ),
        patch(
            "zoho.token_manager.refresh_access_token",
            new_callable=AsyncMock,
            side_effect=ZohoRefreshTokenError("invalid_client_secret"),
        ),
        patch(
            "zoho.token_manager.update_zoho_authorization_status",
            new_callable=AsyncMock,
        ) as mock_update_status,
    ):

        with pytest.raises(
            ZohoRefreshTokenError,
            match="invalid_client_secret",
        ):
            await get_access_token(
                AsyncMock(),
                tenant_id,
                authorization_id,
            )

        mock_update_status.assert_not_awaited()

    assert cache_key not in _token_cache