from typing import Literal
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Agent configs
    REALTIME_PROVIDER: Literal["google", "openai", "pipeline"] = "google"
    REALTIME_VOICE: Literal["Charon", "Fenrir", "Sadachbia", "Enceladus", "Orus", "alloy", "ash", "cedar", "marin", "sage"] = "Fenrir"
    REALTIME_TEMP: float = Field(default=0.8, ge=0.0, le=2.0)
    REALTIME_VISION: bool = True
    REALTIME_USE_BVC: bool = True

    # Guardrails
    REQUIRE_CONFIRM_SENSITIVE: bool = True

    # Logger configs
    LOG_LEVEL: Literal["ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    LOG_DIR: Path = Path("./logs")
    LOG_FILE: str = "output.log"
    LOG_MAX_BYTES: int = Field(default=5_242_880, gt=0, le=2 * 5_242_880)
    LOG_BACKUP_COUNT: int = Field(default=5, ge=1)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
    }


settings = Settings()

REALTIME_PROVIDER = settings.REALTIME_PROVIDER
REALTIME_VOICE = settings.REALTIME_VOICE
REALTIME_TEMP = settings.REALTIME_TEMP
REALTIME_VISION = settings.REALTIME_VISION
REALTIME_USE_BVC = settings.REALTIME_USE_BVC

LOG_LEVEL = settings.LOG_LEVEL
LOG_DIR = settings.LOG_DIR
LOG_FILE = settings.LOG_FILE
LOG_MAX_BYTES = settings.LOG_MAX_BYTES
LOG_BACKUP_COUNT = settings.LOG_BACKUP_COUNT

REQUIRE_CONFIRM_SENSITIVE = settings.REQUIRE_CONFIRM_SENSITIVE
