from urllib.parse import parse_qs, urlparse

from app.config import settings
from zoho.auth import (
    ZOHO_SCOPES,
    build_authorization_url,
    generate_oauth_state,
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