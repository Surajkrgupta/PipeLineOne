from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"

    # YouTube
    yt_client_secrets_file: str = "./secrets/client_secret.json"
    yt_token_file: str = "./secrets/yt_token.json"
    yt_upload_privacy: str = "private"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Pipeline
    require_manual_approval: bool = True
    daily_run_hour: int = 6
    daily_run_minute: int = 30

    # Storage
    database_url: str = "sqlite:///./data/pipeline.db"
    output_dir: str = "./data/runs"


settings = Settings()
