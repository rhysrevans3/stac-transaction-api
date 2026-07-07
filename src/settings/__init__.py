import os
from typing import Literal
import re
from pydantic_settings import BaseSettings, SettingsConfigDict

if os.environ.get("TRANSACTION_AUTHORIZER") == "egi":
    from settings.ceda import CEDAClientSettings as ClientSettings
else:
    from settings.globus import GlobusClientSettings as ClientSettings

DEFAULT_EXTENSIONS = {
    "CMIP6": {
        "CMIP6": {
            "regex": [r"https:\/\/esgf\.github\.io\/stac-transaction-api\/cmip6\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://esgf.github.io/stac-transaction-api/cmip6/v3.0.4/schema.json",
        },
        "alternate_assets": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
    "CMIP6Plus": {
        "CMIP6Plus": {
            "regex": [r"https:\/\/esgf\.github\.io\/stac-transaction-api\/cmip6plus\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://esgf.github.io/stac-transaction-api/cmip6plus/v1.0.4/schema.json",
        },
        "alternate_assets": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
    "CMIP7": {
        "CMIP7": {
            "regex": [r"https:\/\/esgf\.github\.io\/stac-transaction-api\/cmip7\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://esgf.github.io/stac-transaction-api/cmip7/v1.0.0/schema.json",
        },
        "alternate_assets": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
    "CORDEX-CMIP6": {
        "CORDEX-CMIP6": {
            "regex": [r"https:\/\/esgf\.github\.io\/stac-transaction-api\/cordex-cmip6\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://esgf.github.io/stac-transaction-api/cordex-cmip6/v3.1.2/schema.json",
        },
        "alternate_assets": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
    "obs4MIPs": {
        "obs4MIPs": {
            "regex": [r"https:\/\/esgf\.github\.io\/stac-transaction-api\/obs4mips\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://esgf.github.io/stac-transaction-api/obs4mips/v1.0.0/schema.json",
        },
        "alternate_assets": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/alternate-assets\/v[0-9]\.[0-9]\.[0-9]\/schema\.json"],
            "default": "https://stac-extensions.github.io/alternate-assets/v1.2.0/schema.json",
        },
        "file": {
            "regex": [r"https:\/\/stac-extensions\.github\.io\/file\/v[0-9]\.[0-9]\.[0-9]/schema\.json"],
            "default": "https://stac-extensions.github.io/file/v2.1.0/schema.json",
        },
    },
}

VERSION_REGEX = re.compile(
    r"/v("
    r"(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r")/"
)


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
