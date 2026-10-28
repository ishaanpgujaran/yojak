from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Zoho OAuth Configuration
    zoho_client_id: str
    zoho_client_secret: str
    zoho_redirect_uri: str
    zoho_organization_id: str
    zoho_accounts_url: str
    zoho_api_base_url: str
    
    # Database Configuration
    database_url: str

    # WorkOS AuthKit Configuration
    workos_authkit_domain: str

    # Zoho Token Encryption Key
    zoho_token_encryption_key: str


    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8"
    )

settings = Settings()