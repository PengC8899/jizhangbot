from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "HuiYing Ledger Platform V3"
    DOMAIN: str = "api.yourdomain.com"
    SECRET_KEY: str = "supersecretkey"
    TG_MODE: str = "polling" # webhook or polling
    DATABASE_URL: str = "sqlite+aiosqlite:///./huiying.db"

    class Config:
        env_file = ".env"

settings = Settings()
