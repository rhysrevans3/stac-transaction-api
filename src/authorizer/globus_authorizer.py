import hashlib
import logging
import time
from dataclasses import dataclass
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from globus_sdk import AccessTokenAuthorizer, GroupsClient
from globus_sdk.scopes import GroupsScopes
from starlette.middleware.base import BaseHTTPMiddleware

from settings import settings

logger = logging.getLogger("uvicorn.error")

"""
FastAPI Middleware Authorizer
    Authorizer type: FastAPI Middleware
    Event payload: Token
    Token source: Authorization
    Token validation: ^Bearer\\s[^\\s]+$ # noqa: W605
                      ^Bearer\\s[0-9A-Za-z]+$ for access tokens issued by Globus Auth (?)  # noqa: W605
    Authorization caching: 300 seconds (TRANSACTION_CLIENT__AUTHORIZER_CACHE_TTL_SECONDS)
"""

_AUTH_CACHE_MAX_ENTRIES = 2048


@dataclass
class _CachedAuth:
    expires_at: float
    auth: dict


class _AuthTTLCache:
    """In-process TTL cache of authorizer context keyed by access token hash."""

    def __init__(self, max_entries: int = _AUTH_CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: dict[str, _CachedAuth] = {}
        self._lock = Lock()

    @staticmethod
    def _key(access_token: str) -> str:
        return hashlib.sha256(access_token.encode()).hexdigest()

    def get(self, access_token: str) -> dict | None:
        key = self._key(access_token)
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now >= entry.expires_at:
                del self._entries[key]
                return None
            return entry.auth

    def set(self, access_token: str, auth: dict, ttl: int) -> None:
        if ttl <= 0:
            return
        key = self._key(access_token)
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._entries[key] = _CachedAuth(expires_at=expires_at, auth=auth)
            if len(self._entries) > self._max_entries:
                self._evict_expired()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        for key, entry in list(self._entries.items()):
            if now >= entry.expires_at:
                del self._entries[key]


_auth_cache = _AuthTTLCache()


def _cache_ttl_seconds(token_info: dict, max_ttl: int) -> int:
    exp = token_info.get("exp")
    if exp is None:
        return max_ttl
    remaining = int(exp) - int(time.time())
    return max(0, min(max_ttl, remaining))


class GlobusAuthorizer(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health check endpoint for AWS ALB target group
        # Need to bypass authorization for this endpoint
        bypass_paths = ["/favicon.ico", "/healthcheck"]
        if request.url.path in bypass_paths:
            return await call_next(request)

        authorization_header = request.headers.get("authorization")
        if not authorization_header:
            return JSONResponse(
                content={"detail": "Unauthorized - No authorization header"},
                status_code=401,
            )
        if not authorization_header.startswith("Bearer "):
            return JSONResponse(
                content={"detail": "Unauthorized - Invalid authorization header"},
                status_code=401,
            )

        access_token = authorization_header[7:].strip()
        cached_auth = _auth_cache.get(access_token)
        if cached_auth is not None:
            request.state.authorizer = cached_auth
            return await call_next(request)

        response = settings.client.confidential_client.oauth2_token_introspect(access_token, include="identity_set_detail")
        token_info = response.data

        auth_error = self._validate_token_info(token_info)
        if auth_error is not None:
            return auth_error

        groups = self.get_groups(access_token)
        if not groups:
            return JSONResponse(
                content={"detail": "Unauthorized - No active group memberships found"},
                status_code=401,
            )

        auth = {
            "token_info": token_info,
            "groups": groups,
        }
        ttl = _cache_ttl_seconds(token_info, settings.client.authorizer_cache_ttl_seconds)
        _auth_cache.set(access_token, auth, ttl)
        request.state.authorizer = auth
        return await call_next(request)

    def _validate_token_info(self, token_info: dict) -> JSONResponse | None:
        if not token_info.get("active", False):
            return JSONResponse(
                content={"detail": "Unauthorized - Inactive token"},
                status_code=401,
            )

        if settings.client.client_id not in token_info.get("aud", []):
            return JSONResponse(
                content={"detail": "Unauthorized - Invalid token audience"},
                status_code=401,
            )

        if settings.client.scope_string != token_info.get("scope", ""):
            return JSONResponse(
                content={"detail": "Unauthorized - Invalid token scope"},
                status_code=401,
            )

        if settings.client.issuer != token_info.get("iss", ""):
            return JSONResponse(
                content={"detail": "Unauthorized - Invalid token issuer"},
                status_code=401,
            )

        return None

    def get_groups(self, token):
        """
        As https://docs.globus.org/api/auth/specification/#performance states,
        Failure to reuse these tokens can harm performance on both the resource server
        doing the grant and any downstream resource servers it uses.
        Amazon API Gateway Authorization caching setting can be use to cache the authorizer response,
        and if the a new request with the same bearer token
        """

        tokens = settings.client.confidential_client.oauth2_get_dependent_tokens(token, scope=GroupsScopes.view_my_groups_and_memberships)
        groups_token = tokens.by_resource_server[GroupsClient.resource_server]
        authorizer = AccessTokenAuthorizer(groups_token["access_token"])
        groups_client = GroupsClient(authorizer=authorizer)
        groups_response = groups_client.get_my_groups()
        groups = []
        for group in groups_response:
            group_id = group.get("id")
            memberships = group.get("my_memberships", [])
            for membership in memberships:
                if membership.get("status") == "active":
                    groups.append(
                        {
                            "group_id": group_id,
                            "identity_id": membership.get("identity_id"),
                        }
                    )
        return groups
