from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "mysql+pymysql://root:root@localhost/kiddo_app"

    # JWT
    secret_key: str = "your-super-secret-key-change-in-production-please"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # CORS
    allowed_origins: list = ["http://localhost:3000", "http://localhost:5000", "*"]
    firebase_project_id: str = ""
    firebase_credentials_path: str = ""
    admin_allowed_emails: str = ""
    admin_allowed_domains: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def admin_allowed_email_list(self) -> list[str]:
        return [
            email.strip().lower()
            for email in self.admin_allowed_emails.split(",")
            if email.strip()
        ]

    @property
    def admin_allowed_domain_list(self) -> list[str]:
        return [
            domain.strip().lower()
            for domain in self.admin_allowed_domains.split(",")
            if domain.strip()
        ]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
