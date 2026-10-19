import asyncio

from app.database import check_database_connection

def test_database_conncetion():
    result = asyncio.run(check_database_connection())

    assert result is True