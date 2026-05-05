from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ✅ Imports ONLY for static typing
if TYPE_CHECKING:
    from src.settings.ceda import CEDAClientSettings
    from src.settings.globus import GlobusClientSettings

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
    client: Annotated[
        Union["CEDAClientSettings", "GlobusClientSettings"],
        Field(discriminator="client_type"),
    ]

    debug: bool = False

    @model_validator(mode="before")
    @classmethod
    def load_client_config(cls, data: Any) -> Any:
        """
        Lazily import only the selected config model
        based on the discriminator.
        """
        if isinstance(data, dict):
            match data.get("authorizer"):
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

            data["client"] = ClientSettings.model_validate(data["client"])

        return data


from src.settings import ceda, globus

Settings.model_rebuild(
    _types_namespace={
        "CEDAClientSettings": ceda.CEDAClientSettings,
        "OtherClientSettings": globus.GlobusClientSettings,
    }
)
settings = Settings()
