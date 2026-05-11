from typing import Any, Literal

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_EXTENSIONS = {
    "CMIP6": {
        "CMIP6": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/cmip6\/v[0-9]\.[0-9]\.[0-9]/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/cmip6/v1.0.0/schema.json",
        },
        "alternate_assets": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
    "CMIP7": {
        "CMIP7": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/cmip7\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/cmip7/v1.0.0/schema.json",
        },
        "alternate_assets": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [
                r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"
            ],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
}


class Settings(BaseSettings):
    """
    Event Stream Settings
    """

    model_config = SettingsConfigDict(
        env_prefix="TRANSACTION_",
        env_nested_delimiter="__",
        env_file=".env",
    )

    authorizer: Literal["egi", "globus"]
    client: Any

    debug: bool = False

    @field_validator("client", mode="before")
    @classmethod
    def load_client_config(
        cls,
        value: Any,
        info: ValidationInfo,
    ) -> Any:
        """
        Lazily import only the selected config model
        based on the discriminator.
        """
        if isinstance(value, dict):
            match info.data.get("authorizer"):
                case "egi":
                    from src.settings.ceda import (
                        CEDAClientSettings as ClientSettings,
                    )  # pylint: disable=import-outside-toplevel

                case "globus":
                    from src.settings.globus import (
                        GlobusClientSettings as ClientSettings,
                    )  # pylint: disable=import-outside-toplevel

                case other:
                    raise ValueError(f"Unknown authorizer: {other}")

            return ClientSettings.model_validate(value)

        return value


settings = Settings()
