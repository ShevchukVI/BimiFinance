from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "BimiFinance"

    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    DATABASE_URL: str

    # --- Phase 1: Security (fail-fast, див. validate_security) ---
    # Токен Telegram-бота (той самий, що в BimiPal) — для валідації initData Mini App.
    BOT_TOKEN: str = ""
    # Секрет для JWT. Генерація: openssl rand -hex 32
    JWT_SECRET: str = ""
    # Ключ Fernet для шифрування токенів банків. Генерація: Fernet.generate_key()
    FERNET_KEY: str = ""
    # Спільний внутрішній ключ бота (такий самий, як BOT_API_KEY у BimiPal).
    BOT_API_KEY: str = ""
    # Дозволені CORS-origin через кому (Mini App).
    CORS_ORIGINS: str = ""
    # Час життя JWT access-token (годин).
    ACCESS_TOKEN_EXPIRE_HOURS: int = 1
    # Максимальний вік Telegram initData (секунд) для валідації.
    INIT_DATA_MAX_AGE: int = 86400

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_security(self):
        missing = [f for f in ("BOT_TOKEN", "JWT_SECRET", "FERNET_KEY", "BOT_API_KEY") if not getattr(self, f)]
        if missing:
            raise ValueError(
                f"Missing required security settings: {', '.join(missing)}. "
                f"Див. BimiFinance/.env.example"
            )
        return self


settings = Settings()
