from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lab Console"
    database_url: str = "sqlite+aiosqlite:////var/www/lab-console/data/lab_console.db"
    secret_key: str = "change-me-in-production"
    default_location: str = "francecentral"
    default_vm_size: str = "Standard_D4s_v3"
    default_timezone: str = "Europe/Paris"
    schedule_start_hour: int = 7
    schedule_stop_hour: int = 19
    azure_client_id: str = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    azure_public_base_url: str = "https://azurelabs.aguilera.ch"
    azure_redirect_uri: str = ""
    auth_session_ttl_minutes: int = 15
    cors_origins: list[str] = ["*"]

    class Config:
        env_file = "/var/www/lab-console/backend/.env"


settings = Settings()
