from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "dev"
    app_name: str = "llm-gateway"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
settings = Settings()