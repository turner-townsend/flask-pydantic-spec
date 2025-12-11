import logging
from collections.abc import Mapping
from enum import Enum
from typing import Any


class OperationIdType(Enum):
    endpoint_name_short = "endpoint_name_short"
    endpoint_name_full = "endpoint_name_full"
    function_name = "function_name"


class Config:
    """
    :ivar PATH: path for API document page
    :ivar OPENAPI_VERSION: OpenAPI version
    :ivar TITLE: service name
    :ivar VERSION: service version
    :ivar DOMAIN: service host domain
    :ivar VALIDATION_ERROR_CODE: code for validation error responses
    :ivar OPERATION_ID_TYPE: type of operation ID to use in OpenAPI spec
    """

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        self.PATH: str = "apidoc"
        self.FILENAME: str = "openapi.json"
        self.OPENAPI_VERSION: str = "3.1.0"
        self.UI: str = "redoc"
        self._SUPPORT_UI: set[str] = {"redoc", "swagger"}
        self._SUPPORT_MODE: set[str] = {"normal", "strict", "greedy"}
        self.VALIDATION_ERROR_CODE: int = 422
        self.OPERATION_ID_TYPE: OperationIdType = OperationIdType.function_name

        self.TITLE: str = "Service API Document"
        self.VERSION: str = "0.1"
        self.DOMAIN: str | None = None

        self.INFO: dict[str, str] = {}
        self.TAGS: list[Mapping[str, str]] = []

        self.logger = logging.getLogger(__name__)

        self.update(**kwargs)

    @property
    def spec_url(self) -> str:
        return f"/{self.PATH}/{self.FILENAME}"

    def __repr__(self) -> str:
        display = f"\n{self.__class__.__name__:=^80}\n"
        for k, v in vars(self).items():
            if not k.startswith("__"):
                display += f"| {k:<30} {v}\n"

        return display + "=" * 80

    def update(self, **kwargs: Mapping[str, Any]) -> None:
        """
        update config from key-value pairs

        :param kwargs: key(case insensitive)-value pairs for config

        If the key is not in attributes, it will be ignored. Otherwise, the
        corresponding attribute will be updated. (Logging Level: INFO)
        """
        for key, value in kwargs.items():
            key = key.upper()
            if not hasattr(self, key):
                self.logger.info(f'[✗] Ignore unknown attribute "{key}"')
            else:
                setattr(self, key, value)
                self.logger.info(f'[✓] Attribute "{key}" has been updated to "{value}"')

        assert self.UI in self._SUPPORT_UI, "unsupported UI"
