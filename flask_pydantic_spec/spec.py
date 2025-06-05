from collections import defaultdict
from copy import deepcopy
from functools import wraps
from typing import Mapping, Optional, Type, Union, Callable, Iterable, Any, Dict

from flask import Flask, Response as FlaskResponse
from inflection import camelize

from . import Request
from .config import Config
from .flask_backend import FlaskBackend
from .types import BaseModelUnion, RequestBase, ResponseBase
from .utils import (
    get_model_schema,
    parse_comments,
    parse_request,
    parse_params,
    parse_resp,
    default_before_handler,
    default_after_handler,
    get_model_name,
)


def _move_schema_reference(reference: str) -> str:
    if "/definitions" in reference:
        return f"#/components/schemas/{reference.split('/definitions/')[-1]}"
    return reference


class FlaskPydanticSpec:
    """
    Interface

    :param str backend_name: choose from ('flask')
    :param backend: a backend that inherit `flask_pydantic_spec.FlaskBackend`
    :param app: backend framework application instance (you can also register to it later)
    :param before: a callback function of the form :meth:`flask.utils.default_before_handler`
        ``func(req, resp, req_validation_error, instance)``
        that will be called after the request validation before the endpoint function
    :param after: a callback function of the form :meth:`spectree.utils.default_after_handler`
        ``func(req, resp, resp_validation_error, instance)``
        that will be called after the response validation
    :param kwargs: update default :class:`spectree.config.Config`
    """

    def __init__(
        self,
        backend_name: str = "base",
        backend: Type[FlaskBackend] = FlaskBackend,
        app: Optional[Flask] = None,
        before: Callable = default_before_handler,
        after: Callable = default_after_handler,
        **kwargs: Any,
    ):
        self.before: Callable = before
        self.after: Callable = after
        self.config = Config(**kwargs)
        self.backend_name = backend_name
        self.backend = backend(self)
        # init
        self.models: Dict[str, Any] = {}
        if app:
            self.register(app)

    def register(self, app: Flask) -> None:
        """
        register to backend application

        This will be automatically triggered if the app is passed into the
        init step.
        """
        self.app = app
        self.backend.register_route(self.app)

    @property
    def spec(self) -> Mapping[str, Any]:
        """
        get the OpenAPI spec
        """
        if not hasattr(self, "_spec"):
            self._spec = self._generate_spec()
        return self._spec

    def bypass(self, func: Callable) -> bool:
        """Bypass routes not decorated by FlaskPydanticSpec

        In OpenAPI 3.1, it's not valid to have a route that doesn't have at least one
        response attached.
        """
        decorator = getattr(func, "_decorator", None)
        if decorator is None or decorator != self:
            return True
        return False

    def validate(
        self,
        query: Optional[Type[BaseModelUnion]] = None,
        body: Optional[Union[RequestBase, Type[BaseModelUnion]]] = None,
        headers: Optional[Type[BaseModelUnion]] = None,
        cookies: Optional[Type[BaseModelUnion]] = None,
        resp: Optional[ResponseBase] = None,
        tags: Iterable[str] = (),
        deprecated: bool = False,
        before: Optional[Callable] = None,
        after: Optional[Callable] = None,
        extensions: Optional[Dict[str, Any]] = None,
    ) -> Callable:
        """
        - validate query, body, headers in request
        - validate response body and status code
        - add tags to this API route

        :param query: `pydantic.BaseModel`, query in uri like `?name=value`
        :param body: `spectree.Request`, Request body
        :param headers: `pydantic.BaseModel`, if you have specific headers
        :param cookies: `pydantic.BaseModel`, if you have cookies for this route
        :param resp: `spectree.Response`
        :param tags: a tuple of tags string
        :param deprecated: You can mark specific operations as deprecated to indicate that they
                    should be transitioned out of usage
        :param before: :meth:`spectree.utils.default_before_handler` for specific endpoint
        :param after: :meth:`spectree.utils.default_after_handler` for specific endpoint
        :param extensions: a key value map of extension strings
        """

        def decorate_validation(func: Callable) -> Callable:
            @wraps(func)
            def sync_validate(*args: Any, **kwargs: Any) -> FlaskResponse:
                return self.backend.validate(
                    func,
                    query,
                    body if isinstance(body, RequestBase) else Request(body),
                    headers,
                    cookies,
                    resp,
                    before or self.before,
                    after or self.after,
                    *args,
                    **kwargs,
                )

            validation = sync_validate

            # register
            for name, model in zip(
                ("query", "body", "headers", "cookies"), (query, body, headers, cookies)
            ):
                if model is not None:
                    if isinstance(model, RequestBase) and hasattr(model, "model"):
                        _model = getattr(model, "model", None)
                    else:
                        _model = model
                    if _model is not None and not isinstance(_model, RequestBase):
                        self._register_model(_model)
                    setattr(validation, name, model)

            if resp is None:
                raise RuntimeError("must provide at least one response body")

            for model in resp.models:
                self._register_model(model)

            setattr(validation, "resp", resp)

            if tags:
                setattr(validation, "tags", tags)

            if deprecated:
                setattr(validation, "deprecated", True)

            if extensions:
                for key, value in extensions.items():
                    if not key or not key.startswith("x-"):
                        raise ValueError("Swagger vendor extensions must begin with 'x-'")
                setattr(validation, "extensions", extensions)

            # register decorator
            setattr(validation, "_decorator", self)
            return validation

        return decorate_validation

    def _register_model(self, model: Type[BaseModelUnion]) -> None:
        self.models[get_model_name(model)] = self._get_open_api_schema(get_model_schema(model))

    def _generate_spec(self) -> Mapping[str, Any]:
        """
        generate OpenAPI spec according to routes and decorators
        """
        tag_lookup = {tag["name"]: tag for tag in self.config.TAGS}
        routes: Dict[str, Any] = {}
        tags: Dict[str, Any] = {}
        for route in self.backend.find_routes():
            path, parameters = self.backend.parse_path(route)
            routes[path] = routes.get(path, {})
            for method, func in self.backend.parse_func(route):
                if self.backend.bypass(func, method) or self.bypass(func):
                    continue

                operation_id = self.backend.get_operation_id(route, method, func)
                summary, desc = parse_comments(func)
                func_tags = getattr(func, "tags", ())
                for tag in func_tags:
                    if tag not in tags:
                        tags[tag] = tag_lookup.get(tag, {"name": tag})

                routes[path][method.lower()] = {
                    "summary": summary or f"{operation_id} <{method}>",
                    "operationId": camelize(f"{operation_id}", False),
                    "description": desc or "",
                    "tags": getattr(func, "tags", []),
                    "parameters": parse_params(func, parameters[:], self.models),
                    "responses": parse_resp(func, self.config.VALIDATION_ERROR_CODE),
                }
                if hasattr(func, "deprecated"):
                    routes[path][method.lower()]["deprecated"] = True

                extensions = getattr(func, "extensions", {})
                if extensions:
                    routes[path][method.lower()].update(**extensions)

                request_body = parse_request(func)
                if request_body:
                    routes[path][method.lower()]["requestBody"] = self._parse_request_body(
                        request_body
                    )
            if not routes[path]:
                del routes[path]

        spec = {
            "openapi": self.config.OPENAPI_VERSION,
            "info": {
                **self.config.INFO,
                **{
                    "title": self.config.TITLE,
                    "version": self.config.VERSION,
                },
            },
            "tags": sorted(tags.values(), key=lambda t: t["name"]),
            "paths": {**routes},
            "components": {"schemas": {**self._get_model_definitions()}},
        }
        return spec

    def _validate_property(self, property: Mapping[str, Any]) -> Dict[str, Any]:
        allowed_fields = {
            "title",
            "multipleOf",
            "maximum",
            "exclusiveMaximum",
            "minimum",
            "exclusiveMinimum",
            "maxLength",
            "minLength",
            "pattern",
            "maxItems",
            "minItems",
            "uniqueItems",
            "maxProperties",
            "minProperties",
            "required",
            "enum",
            "type",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "items",
            "properties",
            "additionalProperties",
            "description",
            "format",
            "default",
            "nullable",
            "discriminator",
            "readOnly",
            "writeOnly",
            "xml",
            "externalDocs",
            "example",
            "deprecated",
            "$ref",
        }
        result: Dict[str, Any] = defaultdict(dict)

        for key, value in property.items():
            for prop, val in value.items():
                if prop in allowed_fields:
                    result[key][prop] = val

        return result

    def _get_open_api_schema(self, schema: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Convert a Pydantic model into an OpenAPI compliant schema object.
        """
        result = {}
        for key, value in schema.items():
            if key == "properties":
                result[key] = self._validate_property(value)
            else:
                result[key] = value

        return result

    def _get_model_definitions(self) -> Dict[str, Any]:
        """
        handle nested models
        """
        definitions: Dict[str, Any] = {}
        for model, schema in self.models.items():
            if model not in definitions.keys():
                definitions[model] = deepcopy(schema)

            if "$defs" in schema:
                for key, value in schema["$defs"].items():
                    definitions[key] = self._get_open_api_schema(value)
                del schema["$defs"]
                if "$defs" in definitions[model]:
                    del definitions[model]["$defs"]

        return definitions

    def _parse_request_body(self, request_body: Mapping[str, Any]) -> Mapping[str, Any]:
        content_types = list(request_body["content"].keys())
        if len(content_types) != 1:
            raise RuntimeError(
                "Cannot currently handle multiple content types for a single request"
            )
        else:
            content_type = content_types[0]
        schema = request_body["content"][content_type]["schema"]
        if "$ref" not in schema.keys():
            # handle inline schema definitions
            return {"content": {content_type: {"schema": self._get_open_api_schema(schema)}}}
        else:
            return request_body
