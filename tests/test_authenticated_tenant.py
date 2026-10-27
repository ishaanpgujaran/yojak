from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yojak_mcp.server import get_authenticated_tenant


@pytest.mark.anyio
async def test_authenticated_tenant_rejects_missing_token():
    ctx = MagicMock()

    with patch(
        "yojak_mcp.server.get_access_token",
        return_value=None,
    ):
        with pytest.raises(
            PermissionError,
            match="Authentication is Required!",
        ):
            await get_authenticated_tenant(ctx)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "subject",
    [
        None,
        "",
        "   ",
    ],
)
async def test_authenticated_tenant_rejects_missing_subject(subject):
    ctx = MagicMock()
    token = MagicMock()
    token.subject = subject

    with patch(
        "yojak_mcp.server.get_access_token",
        return_value=token,
    ):
        with pytest.raises(
            PermissionError,
            match="Authenticated user identity is missing",
        ):
            await get_authenticated_tenant(ctx)


@pytest.mark.anyio
async def test_authenticated_tenant_uses_verified_subject():
    expected_tenant = {
        "id": "tenant-123",
        "workos_user_id": "user_123",
        "name": "Tenant 123",
    }

    pool = MagicMock()
    ctx = MagicMock()
    ctx.lifespan_context = {"pool": pool}

    token = MagicMock()
    token.subject = "user_123"

    with (
        patch(
            "yojak_mcp.server.get_access_token",
            return_value=token,
        ),
        patch(
            "yojak_mcp.server.get_or_create_tenant",
            new_callable=AsyncMock,
            return_value=expected_tenant,
        ) as mock_get_or_create,
    ):
        tenant = await get_authenticated_tenant(ctx)

    assert tenant == expected_tenant

    mock_get_or_create.assert_awaited_once_with(
        pool,
        "user_123",
    )