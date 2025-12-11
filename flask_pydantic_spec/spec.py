from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from functools import wraps
from operator import itemgetter
from typing import Any

from flask import Blueprint, Flask, jsonify
from flask import Response as FlaskResponse
from flask.blueprints import BlueprintSetupState
from inflection import camelize

from .config import Config
from .flask_backend import FlaskBackend
from .page import PAGES
from .types import BaseModelUnion, Request, RequestBase, ResponseBase
from .utils import (
    default_after_handler,
    default_before_handler,
    get_model_name,
    get_model_schema,
    parse_comments,
    parse_params,
    parse_request,
    parse_resp,
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
        backend: type[FlaskBackend] = FlaskBackend,
        app: Flask | None = None,
        blueprint: Blueprint | None = None,
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
        self.models: dict[str, Any] = {}
        if app:
            self.register(app)
        if blueprint:
            self.register(blueprint)

    def register(
        self,
        app_or_blueprint: Flask | Blueprint,
        register_route: bool = True,
    ) -> None:
        """
        register to backend application

        This will be automatically triggered if the app is passed into the
        init step.
        """
        if isinstance(app_or_blueprint, Flask):
            self.app = app_or_blueprint
            self.backend.app = app_or_blueprint
        elif isinstance(app_or_blueprint, Blueprint):
            self.blueprint = app_or_blueprint
        else:
            raise TypeError(f"unknown type provided {app_or_blueprint.__class__}")

        if register_route:
            self.register_spec_routes(app_or_blueprint)

    def register_spec_routes(self, app_or_blueprint: Flask | Blueprint) -> None:
        app_or_blueprint.add_url_rule(
            self.config.spec_url,
            "openapi",
            lambda: jsonify(self.spec),
        )

        for ui in PAGES:
            app_or_blueprint.add_url_rule(
                f"/{self.config.PATH}/{ui}",
                f"doc_page_{ui}",
                lambda ui=ui: PAGES[ui].format(self.config),
            )

    def for_blueprint(self, blueprint: Blueprint, **kwargs: Any) -> "FlaskPydanticSpec":
        def _record_app(state: BlueprintSetupState) -> None:
            bp_api.register(state.app, register_route=False)

        bp_api = FlaskPydanticSpec(
            backend_name=self.backend_name,
            blueprint=blueprint,
            **kwargs,
        )
        blueprint.record(_record_app)
        return bp_api

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
        query: type[BaseModelUnion] | None = None,
        body: RequestBase | type[BaseModelUnion] | None = None,
        headers: type[BaseModelUnion] | None = None,
        cookies: type[BaseModelUnion] | None = None,
        resp: ResponseBase | None = None,
        tags: Iterable[str] = (),
        deprecated: bool = False,
        before: Callable | None = None,
        after: Callable | None = None,
        extensions: dict[str, Any] | None = None,
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
                ("query", "body", "headers", "cookies"),
                (query, body, headers, cookies),
                strict=True,
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

            validation.resp = resp  # type: ignore[attr-defined]

            if tags:
                validation.tags = tags  # type: ignore[attr-defined]

            if deprecated:
                validation.deprecated = True  # type: ignore[attr-defined]

            if extensions:
                if not all(key and key.startswith("x-") for key in extensions.keys()):
                    raise ValueError("Swagger vendor extensions must begin with 'x-'")
                validation.extensions = extensions  # type: ignore[attr-defined]

            # register decorator
            validation._decorator = self  # type: ignore[attr-defined]
            return validation

        return decorate_validation

    def _register_model(self, model: type[BaseModelUnion]) -> None:
        self.models[get_model_name(model)] = self._get_open_api_schema(get_model_schema(model))

    def _generate_spec(self) -> Mapping[str, Any]:
        """
        generate OpenAPI spec according to routes and decorators
        """
        tag_lookup = {tag["name"]: tag for tag in self.config.TAGS}
        routes: dict[str, Any] = {}
        tags: dict[str, Any] = {}

        if self.app is None:
            raise RuntimeError("Flask app must be registered this instance to generate a spec")

        for route in self.backend.find_routes(self.app):
            path, parameters = self.backend.parse_path(route)
            routes[path] = routes.get(path, {})
            for method, func in self.backend.parse_func(self.app, route):
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
            "paths": dict(sorted(routes.items(), key=itemgetter(0))),
            "components": {
                "schemas": dict(sorted(self._get_model_definitions().items(), key=itemgetter(0)))
            },
        }
        return spec

    def _validate_property(self, property: Mapping[str, Any]) -> dict[str, Any]:
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
        result: dict[str, Any] = defaultdict(dict)

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

    def _get_model_definitions(self) -> dict[str, Any]:
        """
        handle nested models
        """
        definitions: dict[str, Any] = {}
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
