import pytest 

from app.database import lifespan_database

@pytest.mark.anyio
async def test_database_pool():
    async with lifespan_database() as pool:
        result = await pool.fetchval("SELECT 1")

        assert result == 1