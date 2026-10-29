import asyncpg


# Shared reference to the application's database pool
database_pool: asyncpg.Pool | None = None