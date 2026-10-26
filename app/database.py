import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.config import settings


@asynccontextmanager
async def lifespan_database() -> AsyncIterator[asyncpg.Pool]:
    pool = await asyncpg.create_pool(
        dsn = settings.database_url,
        min_size = 1,
        max_size = 5,
        command_timeout = 10,
    )

    try:
        yield pool
    
    finally: 
        await pool.close()


# Database Connecion Check Funtion 
async def check_database_connection() -> bool:
    connection = await asyncpg.connect(
        dsn = settings.database_url
    )

    try:
        result = await connection.fetchval("SELECT 1")
        return result == 1
    
    finally:
        await connection.close()
