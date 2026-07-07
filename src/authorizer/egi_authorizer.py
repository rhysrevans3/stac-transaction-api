import logging
from urllib.parse import urlparse

import httpx
from esgf_core_utils.models.auth import Authorizer
from esgf_core_utils.models.exceptions import InvalidTokenAudienceException
from esgf_core_utils.models.kafka.events import RequesterData
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from settings import settings

logger = logging.getLogger("uvicorn.error")

"""
FastAPI Middleware Authorizer
    Authorizer type: FastAPI Middleware
    Event payload: Token
    Token source: Authorization
    Token validation: ^Bearer\s[^\s]+$                                                    # noqa: W605
                      ^Bearer\s[0-9A-Za-z]+$ for access tokens issued by Globus Auth (?)  # noqa: W605
    Authorization caching: 300 seconds
"""


class EGIAuthorizer(BaseHTTPMiddleware):
    """
    EGI Authorization middleware.
    """

    async def dispatch(self, request: Request, call_next):
        # Need to bypass authorization for this endpoint
        if request.url.path in ["/healthcheck", "/scope"]:
            return await call_next(request)

        logger.debug("Request Headers %s", request.headers)

        auth = httpx.BasicAuth(
            username=settings.client.client_id,
            password=settings.client.client_secret,
        )

        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            logger.debug(
                "Post request to %s",
                settings.client.introspection_endpoint,
            )
            response = await client.post(
                settings.client.introspection_endpoint,
                headers={"Content-type": "application/x-www-form-urlencoded"},
                data=f"token={request.headers.get('authorization')[7:]}",
                auth=auth,
                timeout=5,
            )
            response.raise_for_status()

        token_info = response.json()

        logger.debug("Token info: %s", token_info)

        if request.headers["host"] not in [urlparse(aud).hostname for aud in token_info["aud"]]:
            raise InvalidTokenAudienceException(
                token_audience=request.headers["host"],
                expected_audience=", ".join(token_info["aud"]),
            )

        authorizer = Authorizer(
            regex=settings.client.regex,
            requester_data=RequesterData(
                client_id=token_info["client_id"],
                sub=token_info["sub"],
                iss=token_info["iss"],
            ),
        )

        authorizer.add(token_info["entitlements"])

        request.state.authorizer = authorizer

        return await call_next(request)
