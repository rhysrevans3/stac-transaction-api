import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

if os.environ.get("TRANSACTION_AUTHORIZER") == "egi":
    from settings.ceda import CEDAClientSettings as ClientSettings
else:
    from settings.globus import GlobusClientSettings as ClientSettings


class Settings(BaseSettings):
    """
    Event Stream Settings
    """

    model_config = SettingsConfigDict(
        env_prefix="TRANSACTION_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    authorizer: Literal["egi", "globus"]
    client: ClientSettings
    debug: bool = False


settings = Settings()
