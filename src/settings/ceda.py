from typing import Literal

from pydantic import BaseModel, Field


class CEDAClientSettings(BaseModel):
    """
    CEDA settings
    """

    client_type: Literal["egi"] = Field("egi", frozen=True)

    client_id: str
    client_secret: str
    token_url: str = "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/token"
    introspection_endpoint: str = (
        "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/token/introspect"
    )
    regex: str = (
        r"urn\:mace\:egi\.eu\:group\:esgf.vo.egi.eu\:(?P<type>.*)\:(?P<id>.*)\:role=(?P<role>.*)#aai.egi.eu"
    )
