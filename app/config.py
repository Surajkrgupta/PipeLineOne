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
    # Base64-encoded file contents -- used to reconstruct the real files on
    # hosts like Render where secrets/*.json can't be committed to git (and
    # therefore never reach the container otherwise). See app/startup.py.
    yt_client_secret_b64: str = ""
    yt_token_b64: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # A random string you choose -- set the same value when registering the
    # webhook with Telegram (see README). Telegram echoes it back in a header
    # on every webhook call, letting us reject requests that aren't genuinely
    # from Telegram.
    telegram_webhook_secret: str = ""

    # Pipeline
    require_manual_approval: bool = True
    daily_run_hour: int = 6
    daily_run_minute: int = 30

    # Storage
    database_url: str = "sqlite:///./data/pipeline.db"
    output_dir: str = "./data/runs"


settings = Settings()