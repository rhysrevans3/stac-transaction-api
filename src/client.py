import logging
import uuid
from datetime import datetime
from typing import Optional, Union

from esgf_core_utils.models.auth.egi import EGIAuth
from esgf_core_utils.models.exceptions import (
    AuthorizationException,
    ExpectedExtensionsMissingException,
    MissingPermissionException,
    OperationNotPermittedException,
    RFC9457Exception,
    STACValidationException,
    UnexpectedExtensionException,
    UnknownException,
)
from esgf_core_utils.models.kafka.events import (
    Auth,
    CreatePayload,
    Data,
    KafkaEvent,
    Metadata,
    PatchPayload,
    Publisher,
    RequesterData,
    UpdatePayload,
)
from esgf_core_utils.models.kafka.producer import KafkaProducer
from fastapi import Request, Response, status
from stac_fastapi.extensions.core.transaction import BaseTransactionsClient
from stac_fastapi.extensions.core.transaction.request import PartialItem, PatchOperation
from stac_fastapi.types.stac import Collection
from stac_pydantic.item import Item

from settings import settings
from utils import (
    operation_to_partial_item,
    validate_extensions,
    validate_patch,
    validate_post,
)

# Setup logger
# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")


class TransactionClient(BaseTransactionsClient):

    def __init__(self):
        self.producer = KafkaProducer()

    def allowed_groups(self, properties, acp) -> list:
        if isinstance(acp, list):
            return acp
        for facet, subpolicy in acp.items():
            if hasattr(properties, facet):
                property_value = getattr(properties, facet)
                if isinstance(property_value, str):
                    property_value = [property_value]
                matches = list(set(property_value) & set(subpolicy.keys()))
                for match in matches:
                    groups = self.allowed_groups(properties, subpolicy[match])
                    if groups:
                        return groups
        return []

    def globus_authorize(self, item: Item, request: Request, collection_id: str) -> dict:
        properties = item.properties

        if item.collection != collection_id:
            raise ValueError("Item collection must match path collection_id")
        if getattr(properties, "project", None) != collection_id:
            raise ValueError("Item project must match path collection_id")

        allowed_groups = self.allowed_groups(properties, settings.client.access_control_policy)
        allowed_groups_uuid = [g.get("uuid") for g in allowed_groups]

        authorizer = request.state.authorizer
        token_info = authorizer.get("token_info")
        user_groups = authorizer.get("groups")

        authorized_identities = []
        for group in user_groups:
            if group.get("group_id") in allowed_groups_uuid:
                authorized_identities.append(
                    {
                        "group_id": group.get("group_id"),
                        "identity_id": group.get("identity_id"),
                    }
                )
        if not authorized_identities:
            raise MissingPermissionException(permission_type="globus", target=collection_id)

        requester_data = RequesterData(
            client_id=token_info.get("client_id"),
            sub=token_info.get("sub"),
            iss=token_info.get("iss"),
        )

        logger.info("REQUESTER DATA: %s", requester_data)

        auth = Auth(
            requester_data=requester_data,
        )

        return auth

    def egi_authorize(
        self,
        collection_id: str,
        item: Item | PartialItem,
        role: str,
        request: Request,
        request_id: str,
        event_id: str,
    ) -> Auth:
        """Auhorise request with EGI

        Args:
            item (Item): item to check authorization for
            role (str): role to check authorization for
            request (Request): current request

        Returns:
            Auth: Auth object if successful
        """
        authorizer: EGIAuth = request.state.authorizer
        authorizer.authorize(
            collection_id=collection_id,
            item=item,
            role=role,
            request_id=request_id,
            event_id=event_id,
        )

        logger.info("REQUESTER DATA: %s", authorizer.requester_data)

        return Auth(
            requester_data=authorizer.requester_data.model_dump(),
        )

    def authorize(
        self,
        collection_id: str,
        item: Item | PartialItem,
        role: str,
        request: Request,
        request_id: str,
        event_id: str,
    ) -> Auth:

        if settings.authorizer == "globus":
            return self.globus_authorize(collection_id=collection_id, item=item, request=request)
        else:
            return self.egi_authorize(
                collection_id=collection_id,
                item=item,
                role=role,
                request=request,
                request_id=request_id,
                event_id=event_id,
            )

    async def create_item(
        self,
        collection_id: str,
        item: Item,
        request: Request,
    ) -> Optional[Union[Item, Response, None]]:

        headers = request.headers

        event_id = uuid.uuid4().hex
        request_id = headers.get("x-request-id", uuid.uuid4().hex)

        try:
            auth = self.authorize(
                item=item,
                role="CREATE",
                request=request,
                collection_id=collection_id,
                request_id=request_id,
                event_id=event_id,
            )

        except MissingPermissionException as exc:
            raise AuthorizationException(instance=f"{request_id}:{event_id}") from exc

        item_extensions = item.stac_extensions if item.stac_extensions else []
        try:
            item_extensions = validate_extensions(collection_id=collection_id, item_extensions=item_extensions)
            validate_post(
                event_id=event_id,
                request_id=request_id,
                item_id=item.id,
                item=item,
                extensions=item_extensions,
            )

        except (
            ExpectedExtensionsMissingException,
            OperationNotPermittedException,
            STACValidationException,
            UnexpectedExtensionException,
        ) as exc:
            rfc_exc = RFC9457Exception()
            rfc_exc.status_code = 400
            rfc_exc.type = exc.type
            rfc_exc.title = exc.title
            rfc_exc.detail = exc.detail
            rfc_exc.instance = f"{request_id}:{event_id}"
            raise rfc_exc from exc
        user_agent = headers.get("user-agent", "/").split("/")

        payload = CreatePayload(
            method="POST",
            collection_id=collection_id,
            item=item.model_dump(),
        )

        data = Data(type="STAC", payload=payload)

        publisher = Publisher(package=user_agent[0], version=user_agent[1] if len(user_agent) > 1 else "")

        metadata = Metadata(
            auth=auth,
            event_id=event_id,
            publisher=publisher,
            request_id=request_id,
            time=datetime.now().isoformat(),
            schema_version="1.0.0",
        )
        event = KafkaEvent(metadata=metadata, data=data)

        try:
            self.producer.success(
                key=item.id,
                value=event.model_dump_json().encode("utf8"),
            )

        except Exception as exc:
            logger.error("Error producing message: %s", exc)
            raise UnknownException(instance=f"{request_id}:{event_id}") from exc

        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            content="Item queued for publication",
        )

    async def update_item(
        self,
        collection_id: str,
        item_id: str,
        item: Item,
        request: Request,
    ) -> Optional[Union[Item, Response]]:

        headers = request.headers.get("headers", {})

        event_id = uuid.uuid4().hex
        request_id = headers.get("X-Request-ID", uuid.uuid4().hex)

        auth = self.authorize(
            collection_id=collection_id,
            item=item,
            role="UPDATE",
            request=request,
            request_id=request_id,
            event_id=event_id,
        )

        item_extensions = item.stac_extensions if item.stac_extensions else []

        item_extensions = validate_extensions(collection_id=collection_id, item_extensions=item_extensions)

        validate_post(
            event_id=event_id,
            request_id=request_id,
            item_id=item.id,
            item=item,
            extensions=item_extensions,
        )

        user_agent = headers.get("User-Agent", "/").split("/")

        payload = UpdatePayload(
            method="PUT",
            collection_id=collection_id,
            item_id=item_id,
            item=item.model_dump(),
        )

        data = Data(type="STAC", payload=payload)

        publisher = Publisher(package=user_agent[0], version=user_agent[1] if len(user_agent) > 1 else "")
        metadata = Metadata(
            auth=auth,
            event_id=event_id,
            publisher=publisher,
            request_id=request_id,
            time=datetime.now().isoformat(),
            schema_version="1.0.0",
        )
        event = KafkaEvent(metadata=metadata, data=data)

        try:
            self.producer.success(
                key=item_id,
                value=event.model_dump_json().encode("utf8"),
            )

        except Exception as exc:
            logger.error("Error producing message: %s", exc)
            raise UnknownException(instance=f"{request_id}:{event_id}") from exc

        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            content="Item queued for update",
        )

    async def patch_item(
        self,
        collection_id: str,
        item_id: str,
        patch: Union[PartialItem, list[PatchOperation]],
        request: Request,
    ) -> Optional[Union[Item, Response]]:
        logger.info("PATCH REQUEST: %s", patch)

        item = operation_to_partial_item(collection_id=collection_id, operations=patch) if isinstance(patch, list) else patch

        headers = request.headers.get("headers", {})

        event_id = uuid.uuid4().hex
        request_id = headers.get("X-Request-ID", uuid.uuid4().hex)

        auth = self.authorize(
            collection_id=collection_id,
            item=item,
            role="UPDATE",
            request=request,
            request_id=request_id,
            event_id=event_id,
        )

        item_extensions = item.stac_extensions if item.stac_extensions else []

        item_extensions = validate_extensions(collection_id=collection_id, item_extensions=item_extensions)

        validate_patch(
            event_id=event_id,
            request_id=request_id,
            item_id=item_id,
            item=item,
            extensions=item_extensions,
        )

        user_agent = headers.get("user-agent", "/").split("/")

        payload = PatchPayload(
            method="PATCH",
            collection_id=collection_id,
            item_id=item_id,
            patch=patch.model_dump(),
        )

        data = Data(type="STAC", payload=payload)

        publisher = Publisher(package=user_agent[0], version=user_agent[1] if len(user_agent) > 1 else "")
        metadata = Metadata(
            auth=auth,
            event_id=event_id,
            publisher=publisher,
            request_id=request_id,
            time=datetime.now().isoformat(),
            schema_version="1.0.0",
        )
        event = KafkaEvent(metadata=metadata, data=data)

        try:
            self.producer.success(
                key=item_id,
                value=event.model_dump_json().encode("utf8"),
            )

        except Exception as exc:
            logger.error("Error producing message: %s", exc)
            raise UnknownException(instance=f"{request_id}:{event_id}") from exc

        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            content="Item queued for update",
        )

    async def delete_item(
        self,
        collection_id: str,
        item_id: str,
        request: Request,
    ) -> Optional[Union[Item, Response]]:
        logger.info("DELETE REQUEST: %s %s", collection_id, item_id)

        headers = request.headers.get("headers", {})

        event_id = uuid.uuid4().hex
        request_id = headers.get("x-request-id", uuid.uuid4().hex)

        auth = self.authorize(
            collection_id=collection_id,
            item=item_id,
            role="UPDATE",
            request=request,
            request_id=request_id,
            event_id=event_id,
        )

        user_agent = headers.get("user-agent", "/").split("/")

        payload = PatchPayload(
            method="PATCH",
            collection_id=collection_id,
            item_id=item_id,
            patch=[{"op": "add", "path": "properties.retracted", "value": True}],
        )

        data = Data(type="STAC", payload=payload)

        publisher = Publisher(package=user_agent[0], version=user_agent[1] if len(user_agent) > 1 else "")

        metadata = Metadata(
            auth=auth,
            event_id=event_id,
            publisher=publisher,
            request_id=request_id,
            time=datetime.now().isoformat(),
            schema_version="1.0.0",
        )
        event = KafkaEvent(metadata=metadata, data=data)

        try:
            self.producer.success(
                key=item_id,
                value=event.model_dump_json().encode("utf8"),
            )

        except Exception as exc:
            logger.error("Error producing message: %s", exc)
            raise UnknownException(instance=f"{request_id}:{event_id}") from exc

        return Response(
            status_code=status.HTTP_202_ACCEPTED,
            content="Item queued for deletion",
        )

    async def create_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("create_collection is not implemented")

    async def patch_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("patch_collection is not implemented")

    async def update_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("update_collection is not implemented")

    async def delete_collection(self, collection_id: str, **kwargs) -> None:
        raise NotImplementedError("delete_collection is not implemented")
