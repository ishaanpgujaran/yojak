from urllib.parse import parse_qs, urlparse

from app.config import settings
from zoho.auth import (
    ZOHO_SCOPES,
    build_authorization_url,
    generate_oauth_state,
    REQUIRED_ZOHO_SCOPES,
    get_missing_scopes,
)

def test_oauth_state_is_generated_securely():
    state_one = generate_oauth_state()
    state_two = generate_oauth_state()

    assert isinstance(state_one, str)
    assert len(state_one) > 0
    assert state_one != state_two

def test_authorization_url_contains_required_parameters():
    state = generate_oauth_state()

    authorization_url = build_authorization_url(state)

    parsed_url = urlparse(authorization_url)

    params = parse_qs(parsed_url.query)

    assert parsed_url.scheme == "https"
    assert params["client_id"] == [settings.zoho_client_id]
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [settings.zoho_redirect_uri]
    assert params["access_type"] == ["offline"]
    assert params["state"] == [state]
    assert params["scope"] == [ZOHO_SCOPES]



# ---------------------------------------------------------
# Test 3: All required scopes are granted
# ---------------------------------------------------------

def test_get_missing_scopes_when_all_required_scopes_are_granted():

    granted_scopes = list(REQUIRED_ZOHO_SCOPES)

    missing_scopes = get_missing_scopes(granted_scopes)

    assert missing_scopes == set()


# ---------------------------------------------------------
# Test 4: One required scope is missing
# ---------------------------------------------------------

def test_get_missing_scopes_when_one_scope_is_missing():

    granted_scopes = [
        "ZohoInventory.items.READ",
        "ZohoInventory.salesorders.READ",
    ]

    missing_scopes = get_missing_scopes(granted_scopes)

    assert missing_scopes == {
        "ZohoInventory.settings.READ"
    }


# ---------------------------------------------------------
# Test 5: Multiple required scopes are missing
# ---------------------------------------------------------

def test_get_missing_scopes_when_multiple_scopes_are_missing():

    granted_scopes = [
        "ZohoInventory.items.READ",
    ]

    missing_scopes = get_missing_scopes(granted_scopes)

    assert missing_scopes == {
        "ZohoInventory.salesorders.READ",
        "ZohoInventory.settings.READ",
    }


# ---------------------------------------------------------
# Test 6: Extra granted scopes do not cause a failure
# ---------------------------------------------------------

def test_get_missing_scopes_with_extra_granted_scopes():

    granted_scopes = [
        "ZohoInventory.items.READ",
        "ZohoInventory.salesorders.READ",
        "ZohoInventory.settings.READ",
        "ZohoInventory.contacts.READ",
    ]

    missing_scopes = get_missing_scopes(granted_scopes)

    assert missing_scopes == set()


# ---------------------------------------------------------
# Test 7: Whitespace, duplicates and invalid values
# ---------------------------------------------------------

def test_get_missing_scopes_handles_whitespace_duplicates_and_invalid_values():

    granted_scopes = [
        " ZohoInventory.items.READ ",
        "ZohoInventory.items.READ",
        None,
        "",
        "   ",
        123,
    ]

    missing_scopes = get_missing_scopes(granted_scopes)

    assert missing_scopes == {
        "ZohoInventory.salesorders.READ",
        "ZohoInventory.settings.READ",
    }
