import json
import logging
import re

import httpx
import jsonschema
from esgf_core_utils.models.exceptions import (
    ExpectedExtensionsMissingException,
    OperationNotPermittedException,
    STACValidationException,
    UnexpectedExtensionException,
)
from jsonschema.protocols import Validator
from stac_fastapi.extensions.core.transaction.request import (
    PartialItem,
    PatchAddReplaceTest,
    PatchOperation,
)
from stac_pydantic.item import Item

from settings import DEFAULT_EXTENSIONS

# Setup logger
logger = logging.getLogger("uvicorn.error")


def operation_to_partial_item(collection_id: str, operations: list[PatchOperation]) -> PartialItem:
    """Convert operations to partial item

    Args:
        collection_id (str): ID of Item's Collection.
        operations (list[PatchOperation]): List of operations to be converted to PartialItem

    Raises:
        OperationNotPermittedException: Move & Copy operatations not permitted

    Returns:
        PartialItem: Partial item equivalent to operations
    """
    item = {}

    for operation in operations:

        if operation.op == "remove":
            operation = PatchAddReplaceTest(op="add", path=operation.path, value=None)

        if operation.op in ["add", "replace"]:
            if operation.path.lstrip("/") == "stac_extensions":
                validate_extensions(
                    collection_id=collection_id,
                    item_extensions=operation.value,
                    strict=True,
                )

            path_parts = operation.path.lstrip("/").split("/")

            if isinstance(path_parts[-1], int):
                path_parts.remove(-1)
                nest = [operation.value]

            else:
                nest = operation.value

            if isinstance(nest, list):
                existing = item.copy()
                for path_part in path_parts:
                    existing = existing.get(path_part, {})

                if existing:
                    nest.extend(existing)

            for path_part in reversed(path_parts):
                nest = {path_part: nest}

            item |= nest

        if operation.op in ["move", "copy"]:
            # May need to update this for alternat asset updates
            raise OperationNotPermittedException(op=operation.op)

    return PartialItem.model_validate(item)


def validate_extensions(collection_id: str, item_extensions: list[str], strict: bool = False) -> list[str]:
    """Validate expected default extensions are present.

    Args:
        collection_id (str): ID of Item's Collection.
        item_extensions (list[str]): Given list of extensions.
        strict (bool): if True Exception is raised if expected extensions are missing.

    Raises:
        UnexpectedExtensionException: Unexpected extensions
        ExpectedExtensionsMissingException: Expected extension missing

    Returns:
        list[str]: list of extensions including defaults
    """

    expected_extensions = DEFAULT_EXTENSIONS.get(collection_id, {}).copy()

    for item_extension in item_extensions:
        expected = False
        for (
            expected_extension_key,
            expected_extension,
        ) in expected_extensions.copy().items():
            if any(re.compile(regex).match(str(item_extension)) for regex in expected_extension["regex"]):
                expected_extensions.pop(expected_extension_key)
                expected = True

        if not expected:
            raise UnexpectedExtensionException(extension=item_extension)

    missing_extensions = [expected_extension["default"] for expected_extension in expected_extensions.values()]

    if strict & len(missing_extensions) > 0:
        raise ExpectedExtensionsMissingException(extensions=missing_extensions)

    item_extensions.extend(missing_extensions)

    return item_extensions


def get_null_keys(item: PartialItem) -> tuple[PartialItem, set[str]]:
    """Remove and list null value keys from PatialItem.

    Args:
        item (dict): Item dictionary to be updated

    Returns:
        tuple[dict, list[str]]: The PartialItem with nulls removed and list of null keys
    """

    def nested_null_keys(d: dict) -> tuple[dict, set[str]]:
        null_keys = set()
        for k, v in d.items():

            if v is None:
                del d[k]
                null_keys.add(k)

            if isinstance(v, dict):
                sub_dict, sub_null_keys = nested_null_keys(v)
                null_keys.update(sub_null_keys)
                d[k] = sub_dict

        return d, null_keys

    item_dict, null_keys = nested_null_keys(item.model_dump())
    item = PartialItem.model_validate(item_dict)

    return item, null_keys


def get_extension_validator(extension: str) -> Validator:
    """Get JSON schema validator for an extension.

    Args:
        extension (str): Extension URI

    Returns:
        Validator: Validator for extension
    """
    schema = httpx.get(extension).json()
    # This block is cribbed (w/ change in error handling) from
    # jsonschema.validate
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def validate_patch(
    item_id: str,
    item: PartialItem,
    extensions: list[str],
) -> None:
    """Validate a PartialItem patch request

    Args:
        item_id (str): ID of the item to validate
        item (PartialItem): Partial Item to be validated to validate
        extensions (list[str]): List of STAC extensions to be validated against

    Raises:
        STACValidationException: Validation error
        UnexpectedExtensionException: Unexpect exception with validation
    """
    item, null_keys = get_null_keys(item)

    for extension in extensions:
        extension_validator = get_extension_validator(str(extension))

        required_keys = set()
        raise_errors = []
        for error in extension_validator.iter_errors(json.loads(item.model_dump_json())):

            if error.validator in ["oneOf"]:
                continue

            elif error.validator == "required":
                required_keys.add(json.dumps(error.validator_value))

            else:
                raise_errors.append(error)

        for null_key_error in required_keys & null_keys:
            raise_errors.append(f"Variable {null_key_error} is required and cannot be removed")

        if raise_errors:
            logger.error(f"STAC validation error: {item_id}")

            raise STACValidationException()


def validate_post(
    event_id: str,
    request_id: str,
    item_id: str,
    item: Item,
    extensions: list[str],
) -> None:
    """Validate a Item post request

    Args:
        event_id (str): ID of the Kafka event
        request_id (str): ID of the request
        item_id (str): ID of the item to validate
        item (Item): Partial Item to be validated to validate
        extensions (list[str]): List of STAC extensions to be validated against

    Raises:
        STACValidationException: Validation error
    """
    for extension in extensions:
        extension_validator = get_extension_validator(str(extension))

        raise_errors = []
        for error in extension_validator.iter_errors(json.loads(item.model_dump_json())):
            raise_errors.append(error)

        if raise_errors:
            logger.error(f"STAC validation error: {item_id}")

            raise STACValidationException()
