import logging
from typing import Set, Optional, Dict, Any, Mapping, List


class Config:
    """Class for configuring Flask-Pydantic-Spec.

    To customise the behaviour of Flask-Pydantic-Spec, you can override the defaults by passing in arguments here

    Args:
        PATH: The location you would like the OpenAPI documentation available on - defaults to 'apidoc'
        FILENAME: The name of the generated OpenAPI documentation - defaults to 'openapi.json'
        OPENAPI_VERSION: The version of OpenAPI you want to generate - defaults to '3.0.3'
        UI: Which OpenAPI doc explorer you would like to use - either 'redoc' or 'swagger'
        MODE: Defines how Flask-Pydantic-Spec will gather routes and models for including in the OpenAPI spec.
        INLINE_DEFINITIONS: Whether or not to generate query/body arguments inline or as reference objects - defaults
            to True.
        VALIDATION_ERROR_CODE: What error code you would like to return when Pydantic validation fails - defaults to
            422.
        TITLE: The title of your OpenAPI document - defaults to 'Service API Document'
        VERSION: The version of your OpenAPI spec.
        DOMAIN: Optional location of the API your OpenAPI documentation refers to
        INFO: Extra information to insert into your OpenAPI document.
        TAGS: A list of mapping of tag name to tag description for your OpenAPI document.
    """

    def __init__(self, **kwargs: Dict[str, Any]) -> None:
        self.PATH: str = "apidoc"
        self.FILENAME: str = "openapi.json"
        self.OPENAPI_VERSION: str = "3.0.3"
        self.UI: str = "redoc"
        self._SUPPORT_UI: Set[str] = {"redoc", "swagger"}
        self.MODE: str = "normal"
        self.INLINE_DEFINITIONS: bool = True
        self._SUPPORT_MODE: Set[str] = {"normal", "strict", "greedy"}
        self.VALIDATION_ERROR_CODE: int = 422

        self.TITLE: str = "Service API Document"
        self.VERSION: str = "0.1"
        self.DOMAIN: Optional[str] = None

        self.INFO: Dict[str, str] = {}
        self.TAGS: List[Mapping[str, str]] = []

        self.logger = logging.getLogger(__name__)

        self.update(**kwargs)

    @property
    def spec_url(self) -> str:
        return f"/{self.PATH}/{self.FILENAME}"

    def __repr__(self) -> str:
        display = "\n{:=^80}\n".format(self.__class__.__name__)
        for k, v in vars(self).items():
            if not k.startswith("__"):
                display += "| {:<30} {}\n".format(k, v)

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
        assert self.MODE in self._SUPPORT_MODE, "unsupported MODE"
