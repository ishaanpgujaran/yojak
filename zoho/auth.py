import secrets
from urllib.parse import urlencode

from app.config import settings

ZOHO_AUTH_URL = (f"{settings.zoho_accounts_url.rstrip('/')}/oauth/v2/auth")

ZOHO_SCOPES = (
    "ZohoInventory.items.READ,"
    "ZohoInventory.salesorders.READ,"
    "ZohoInventory.settings.READ"
)


# 1. Generate a Cryptographically secure OAuth State value
def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


# 2. Build the Zoho Authorization URL 
def build_authorization_url(state:str) -> str:
    params = {
        "scope" : ZOHO_SCOPES,
        "client_id" : settings.zoho_client_id,
        "response_type" : "code",
        "redirect_uri" : settings.zoho_redirect_uri,
        "access_type" : "offline",
        "state" : state,
    }

    query_string = urlencode(params)

    return f"{ZOHO_AUTH_URL}?{query_string}"