from pydantic import BaseModel


class CEDAClientSettings(BaseModel):
    """
    CEDA settings
    """

    client_id: str
    client_secret: str
    token_url: str = "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/token"
    introspection_endpoint: str = "https://aai.egi.eu/auth/realms/egi/protocol/openid-connect/token/introspect"
    regex: str = (
        r"urn\:mace\:egi\.eu\:group\:esgf.vo.egi.eu\:(?P<type>[^:]*)\:(?P<id>[^:]*)"
        r"(\:institution\:(?P<institution>[^:]*))?\:role=(?P<role>[^:]*)#aai\.egi\.eu"
    )
    scope: str = "offline_access entitlements"
