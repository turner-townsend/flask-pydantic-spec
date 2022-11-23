from functools import wraps
from typing import Mapping, Optional, Type, Union, Callable, Iterable, Any, Dict

from flask import Flask, Response as FlaskResponse
from pydantic import BaseModel
from inflection import camelize

from . import Request
from .config import Config
from .flask_backend import FlaskBackend
from .types import RequestBase, ResponseBase
from .utils import (
    parse_comments,
    parse_request,
    parse_params,
    parse_resp,
    parse_name,
    default_before_handler,
    default_after_handler,
    get_open_api_schema,
)


class FlaskPydanticSpec:
    """
    Interface

    :param str backend_name: choose from ('flask')
    :param backend: a backend that inherit `flask_pydantic_spec.FlaskBackend`
    :param app: backend framework application instance (you can also register to it later)
    :param before: a callback function of the form :meth:`fla.utils.default_before_handler`
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
        """
        bypass rules for routes (mode defined in config)

        :normal:    collect all the routes that are not decorated by other
                    `SpecTree` instance
        :greedy:    collect all the routes
        :strict:    collect all the routes decorated by this instance
        """
        if self.config.MODE == "greedy":
            return False
        elif self.config.MODE == "strict":
            if getattr(func, "_decorator", None) == self:
                return False
            return True
        else:
            decorator = getattr(func, "_decorator", None)
            if decorator and decorator != self:
                return True
            return False

    def validate(
        self,
        query: Optional[Type[BaseModel]] = None,
        body: Optional[Union[RequestBase, Type[BaseModel]]] = None,
        headers: Optional[Type[BaseModel]] = None,
        cookies: Optional[Type[BaseModel]] = None,
        resp: Optional[ResponseBase] = None,
        tags: Iterable[str] = (),
        deprecated: bool = False,
        before: Optional[Callable] = None,
        after: Optional[Callable] = None,
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
        :param deprecated: You can mark specific operations as deprecated to indicate that they should be transitioned out of usage
        :param before: :meth:`spectree.utils.default_before_handler` for specific endpoint
        :param after: :meth:`spectree.utils.default_after_handler` for specific endpoint
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
                ("query", "body", "headers", "cookies"),
                (query, body, headers, cookies),
            ):
                if model is not None:
                    if hasattr(model, "model"):
                        _model = getattr(model, "model", None)
                    else:
                        _model = model
                    if _model:
                        self.models[_model.__name__] = get_open_api_schema(
                            _model.schema()
                        )
                    setattr(validation, name, model)

            if resp:
                for model in resp.models:
                    if model:
                        assert not isinstance(model, RequestBase)
                        self.models[model.__name__] = get_open_api_schema(
                            model.schema()
                        )
                setattr(validation, "resp", resp)

            if tags:
                setattr(validation, "tags", tags)

            if deprecated:
                setattr(validation, "deprecated", True)

            # register decorator
            setattr(validation, "_decorator", self)
            return validation

        return decorate_validation

    def _generate_spec(self) -> Mapping[str, Any]:
        """
        generate OpenAPI spec according to routes and decorators
        """
        tag_lookup = {tag["name"]: tag for tag in self.config.TAGS}
        routes: Dict[str, Any] = {}
        tags: Dict[str, Any] = {}
        param_objects: Dict[str, Any] = {}

        for route in self.backend.find_routes():
            path, parameters = self.backend.parse_path(route)
            routes[path] = routes.get(path, {})
            for method, func in self.backend.parse_func(route):
                if self.backend.bypass(func, method) or self.bypass(func):
                    continue

                name = parse_name(func)
                summary, desc = parse_comments(func)
                func_tags = getattr(func, "tags", ())
                for tag in func_tags:
                    if tag not in tags:
                        tags[tag] = tag_lookup.get(tag, {"name": tag})

                params = parse_params(func, self.config.INLINE_DEFINITIONS)
                responses = parse_resp(func, self.config.VALIDATION_ERROR_CODE)
                body = parse_request(func)

                if not any([params, responses, body]):
                    raise ValueError(
                        f"No definitions in OpenAPI spec for route '{name} <{method}>'"
                    )

                current_path = routes[path]
                method_key = method.lower()

                current_path[method_key] = {
                    "summary": summary or f"{name} <{method}>",
                    "operationId": camelize(f"{name}", False),
                    "description": desc or "",
                    "tags": getattr(func, "tags", []),
                    "responses": responses,
                    "parameters": [],
                }
                if not self.config.INLINE_DEFINITIONS:
                    current_path[method_key]["parameters"] = [
                        {"$ref": f"#/components/parameters/{model_name}"}
                        for location in params.values()
                        for model_name in location
                    ]
                    param_objects.update(
                        {
                            model_name: schema
                            for param in params.values()
                            for model_name, schema in param.items()  # type: ignore
                        }
                    )
                else:
                    for location, model in params.items():
                        for schema in model.values():  # type: ignore
                            current_path[method_key]["parameters"].extend(schema)
                if body:
                    routes[path][method_key]["requestBody"] = self._parse_request_body(
                        body
                    )

                if hasattr(func, "deprecated"):
                    routes[path][method_key]["deprecated"] = True
        spec = {
            "openapi": self.config.OPENAPI_VERSION,
            "info": {
                **self.config.INFO,
                **{
                    "title": self.config.TITLE,
                    "version": self.config.VERSION,
                },
            },
            "tags": list(tags.values()),
            "paths": {**routes},
            "components": {"schemas": {**self._get_model_definitions()}},
        }
        if not self.config.INLINE_DEFINITIONS:
            spec["components"]["parameters"] = param_objects  # type: ignore
        return spec

    def _get_model_definitions(self) -> Dict[str, Any]:
        """
        handle nested models
        """
        definitions: Dict[str, Any] = {}
        for model, schema in self.models.items():
            if model not in definitions.keys():
                definitions[model] = schema
            if "definitions" in schema:
                for key, value in schema["definitions"].items():
                    definitions[key] = get_open_api_schema(value)
                del schema["definitions"]

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
            return {"content": {content_type: {"schema": get_open_api_schema(schema)}}}
        else:
            return request_body
