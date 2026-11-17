
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database_errors import DATABASE_AVAILABILITY_ERRORS
from app.main import (
    app as main_app,
    database_availability_exception_handler,
)


# ---------------------------------------------------------
# Test 1: Verify that the main Yojak application has
# registered the database availability exception handler.
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "exception_class",
    DATABASE_AVAILABILITY_ERRORS,
)
def test_main_app_registers_database_exception_handler(exception_class):

    registered_handler = main_app.exception_handlers.get(exception_class)

    assert registered_handler is database_availability_exception_handler


# ---------------------------------------------------------
# Test 2: Simulate each supported database availability
# exception and verify that the handler returns HTTP 503.
#
# We use a separate FastAPI test application so that these
# tests do not modify Yojak's actual application or database.
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "exception_class",
    DATABASE_AVAILABILITY_ERRORS,
)
def test_database_availability_exception_returns_503(exception_class):

    # Create an isolated application for this test.
    test_app = FastAPI()

    # Register the same handler used by Yojak.
    test_app.add_exception_handler(
        exception_class,
        database_availability_exception_handler,
    )

    # Create a temporary endpoint that simulates a database failure.
    @test_app.get("/test-database-error")
    async def trigger_database_error():
        raise exception_class("Simulated database failure")

    # Prevent the test client from re-raising the simulated exception.
    with TestClient(
        test_app,
        raise_server_exceptions=False,
    ) as client:

        response = client.get("/test-database-error")

    # Verify the response status.
    assert response.status_code == 503

    # Verify the response contains the expected safe message.
    assert response.json() == {
        "status": "service_unavailable",
        "message": (
            "Database service is temporarily unavailable. "
            "Please try again later."
        ),
    }

    # Ensure internal exception details are not exposed.
    assert "Simulated database failure" not in response.text


# ---------------------------------------------------------
# Test 3: Verify that unrelated exceptions are not
# incorrectly treated as database availability failures.
# ---------------------------------------------------------

def test_unrelated_exception_is_not_converted_to_503():

    test_app = FastAPI()

    # Register only the database availability handlers.
    for exception_class in DATABASE_AVAILABILITY_ERRORS:
        test_app.add_exception_handler(
            exception_class,
            database_availability_exception_handler,
        )

    # Simulate an unrelated application error.
    @test_app.get("/test-unrelated-error")
    async def trigger_unrelated_error():
        raise RuntimeError("Simulated application failure")

    with TestClient(
        test_app,
        raise_server_exceptions=False,
    ) as client:

        response = client.get("/test-unrelated-error")

    # An unrelated exception should remain an HTTP 500,
    # rather than being classified as a database HTTP 503.
    assert response.status_code == 500
