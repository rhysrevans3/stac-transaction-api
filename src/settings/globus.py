from typing import Any, Self

from globus_sdk import ConfidentialAppAuthClient
from pydantic import BaseModel, model_validator


class GlobusClientSettings(BaseModel):
    """
    Globus settings
    """

    client_id: str
    client_secret: str
    issuer: str
    scope_string: str

    confidential_client: Any

    policy_path: str
    authorizer_cache_ttl_seconds: int = 300
    policy_cache_ttl_seconds: int = 300
    regex: str = r"(?P<type>[^:]*)\:(?P<id>[^:]*)(\:institution\:(?P<institution>[^:]*))?" r"\:role=(?P<role>[^:]*)\:group\:(?P<group_id>[^:]*)"

    @model_validator(mode="before")
    @classmethod
    def pre_load(self, data: dict) -> Self:
        """
        Create confidential_client.
        """
        data["confidential_client"] = ConfidentialAppAuthClient(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
        )

        return data
