from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    BOT_TOKEN: str
    ALLOWED_USERS: str = "699062182"
    WEBAPP_URL: str = "https://freezbipwnz.github.io/candelaTGapp/"

    @property
    def allowed_user_ids(self) -> List[int]:
        return [int(uid.strip()) for uid in self.ALLOWED_USERS.split(",") if uid.strip().isdigit()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
