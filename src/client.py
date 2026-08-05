import logging
import uuid
from datetime import datetime
from typing import Optional, Union

from esgf_core_utils.models.auth import Authorizer
from esgf_core_utils.models.exceptions import (
    AuthorizationException,
    ExpectedExtensionsMissingException,
    ExtensionBelowMinimumException,
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
)
from esgf_core_utils.models.kafka.producer import KafkaProducer
from esgf_core_utils.models.validation import (
    evaluate_patch,
    operation_to_partial_item,
    patch_adapter,
    validate_extensions,
    validate_patch,
    validate_post,
)
from fastapi import Request, Response, status
from stac_fastapi.extensions.transaction import BaseTransactionsClient
from stac_fastapi.extensions.transaction.request import PartialItem, PatchOperation
from stac_fastapi.types.stac import Collection
from stac_pydantic.item import Item

# Setup logger
# logger = logging.getLogger(__name__)
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.DEBUG)


class TransactionClient(BaseTransactionsClient):

    def __init__(self):
        self.producer = KafkaProducer()

    def authorize(
        self,
        collection_id: str,
        item: Item | PartialItem,
        role: str,
        request: Request,
        request_id: str,
        event_id: str,
    ) -> Auth:
        """Authorize request with ESGF Core Utils Authorizer

        Args:
            item (Item): item to check authorization for
            role (str): role to check authorization for
            request (Request): current request

        Returns:
            Auth: Auth object if successful
        """
        authorizer: Authorizer = request.state.authorizer
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

    async def create_item(
        self,
        collection_id: str,
        item: Item,
        request: Request,
    ) -> Optional[Union[Item, Response, None]]:

        logger.debug("CREATE REQUEST: %s", item.model_dump_json())
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

        try:
            item_extensions = validate_extensions(
                collection_id=collection_id,
                item_extensions=item.stac_extensions or [],
            )

            validate_post(
                item_id=item.id,
                item=item,
                extensions=item_extensions,
            )

        except (
            ExpectedExtensionsMissingException,
            OperationNotPermittedException,
            STACValidationException,
            UnexpectedExtensionException,
            ExtensionBelowMinimumException,
        ) as exc:
            logger.error("Error producing message for %s: %s", item.id, exc)
            logger.error("Item model dump: %s", item.model_dump_json())
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
            logger.error("Error producing message for %s: %s", item.id, exc)
            logger.error("Item model dump: %s", item.model_dump_json())
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
        raise NotImplementedError("update_item is not implemented")

    async def patch_item(
        self,
        collection_id: str,
        item_id: str,
        patch: PartialItem | list[PatchOperation],
        request: Request,
    ) -> Item | Response | None:
        logger.info("PATCH REQUEST: %s", patch)

        item = operation_to_partial_item(collection_id=collection_id, operations=patch) if isinstance(patch, list) else patch

        headers = request.headers.get("headers", {})

        event_id = uuid.uuid4().hex
        request_id = headers.get("X-Request-ID", uuid.uuid4().hex)

        role = evaluate_patch(patch)

        logger.debug("PATCH ROLE: %s", role)

        auth = self.authorize(
            collection_id=collection_id,
            item=item,
            role=role,
            request=request,
            request_id=request_id,
            event_id=event_id,
        )

        item_extensions = item.stac_extensions if item.stac_extensions else []
        try:

            item_extensions = validate_extensions(collection_id=collection_id, item_extensions=item_extensions)

            validate_patch(
                item_id=item_id,
                item=item,
                extensions=item_extensions,
            )
        except (
            ExpectedExtensionsMissingException,
            OperationNotPermittedException,
            STACValidationException,
            UnexpectedExtensionException,
            ExtensionBelowMinimumException,
        ) as exc:
            rfc_exc = RFC9457Exception()
            rfc_exc.status_code = 400
            rfc_exc.type = exc.type
            rfc_exc.title = exc.title
            rfc_exc.detail = exc.detail
            rfc_exc.instance = f"{request_id}:{event_id}"
            raise rfc_exc from exc

        user_agent = headers.get("user-agent", "/").split("/")

        payload = PatchPayload(
            method="PATCH",
            collection_id=collection_id,
            item_id=item_id,
            patch=patch_adapter.dump_python(patch),
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
        raise NotImplementedError("delete_item is not implemented")

    async def create_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("create_collection is not implemented")

    async def patch_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("patch_collection is not implemented")

    async def update_collection(self, collection: Collection, **kwargs) -> Collection:
        raise NotImplementedError("update_collection is not implemented")

    async def delete_collection(self, collection_id: str, **kwargs) -> None:
        raise NotImplementedError("delete_collection is not implemented")
