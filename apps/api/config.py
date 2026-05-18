from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "meetbuddy"
    storage_secret_key: str = "meetbuddy123"
    storage_bucket: str = "meetbuddy"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    llm_provider: str = "ollama"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    whisper_model: str = "base"
    hf_token: str = ""

    next_public_api_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
