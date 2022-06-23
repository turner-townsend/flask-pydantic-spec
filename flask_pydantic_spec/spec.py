from collections import defaultdict
from functools import wraps
from typing import Mapping, Optional, Type, Union, Callable, Iterable, Any, Dict, cast

from flask import Flask, Response as FlaskResponse
from pydantic import BaseModel
from inflection import camelize
from nested_lookup import nested_alter

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
        self.class_view_api_info = dict()  # class view info when adding validate decorator
        self.class_view_apispec = dict()  # convert class_view_api_info into openapi spec

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

    def bypass_unpublish(self, func: Callable) -> bool:
        """ bypass unpublished APIs under publish_only mode"""
        if self.config.MODE == "publish_only":
            return not getattr(func, "publish", False)

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
        publish: bool = False,
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
        :param publish: publish api to api doc (only for class based flask view)
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

            class_view = False
            params = []
            if "." in func.__qualname__:
                class_view = True
                view_name, method = func.__qualname__.split(".")
                if view_name not in self.class_view_api_info:
                    self.class_view_api_info[view_name] = {method: {}}
                else:
                    self.class_view_api_info[view_name][method] = {}
                summary, desc = parse_comments(func)
                self.class_view_api_info[view_name][method]["publish"] = publish
                self.class_view_api_info[view_name][method]["summary"] = summary
                self.class_view_api_info[view_name][method]["description"] = desc
                self.class_view_api_info[view_name][method]["responses"] = {
                    "200": {"description": "ok"}
                }

            # register
            for name, model in zip(
                ("query", "body", "headers", "cookies"), (query, body, headers, cookies)
            ):
                if model is not None:
                    if hasattr(model, "model"):
                        _model = getattr(model, "model", None)
                    else:
                        _model = model
                    if _model:
                        self.models[_model.__name__] = self._get_open_api_schema(_model.schema())
                    setattr(validation, name, model)

                    if class_view:
                        model_schema = self._get_open_api_schema(_model.schema())
                        for param_name, schema in model_schema["properties"].items():
                            params.append(
                                {
                                    "name": param_name,
                                    "in": name,
                                    "schema": schema,
                                    "required": name in model_schema.get("required", []),
                                }
                            )

                if class_view:
                    self.class_view_api_info[view_name][method]["parameters"] = [
                        param for param in params if param["in"] == "query"
                    ]
                    if hasattr(validation, "body"):
                        self.class_view_api_info[view_name][method]["requestBody"] = parse_request(
                            validation
                        )

            if resp:
                for model in resp.models:
                    if model:
                        assert not isinstance(model, RequestBase)
                        self.models[model.__name__] = self._get_open_api_schema(model.schema())
                        if class_view:
                            for k, v in resp.generate_spec().items():
                                self.class_view_api_info[view_name][method]["responses"][k] = v
                setattr(validation, "resp", resp)

            if tags:
                setattr(validation, "tags", tags)
                if class_view:
                    self.class_view_api_info[view_name][method]["tags"] = tags

            if deprecated:
                setattr(validation, "deprecated", True)

            # register decorator
            setattr(validation, "_decorator", self)
            setattr(validation, "publish", publish)
            return validation

        return decorate_validation

    def _generate_spec(self) -> Mapping[str, Any]:
        """
        generate OpenAPI spec according to routes and decorators
        """
        tag_lookup = {tag["name"]: tag for tag in self.config.TAGS}
        routes: Dict[str, Any] = {}
        tags: Dict[str, Any] = {}
        for route in self.backend.find_routes():
            path, parameters = self.backend.parse_path(route)
            for method, func in self.backend.parse_func(route):
                if self.backend.bypass(func, method) or self.bypass(func):
                    continue

                name = parse_name(func)
                summary, desc = parse_comments(func)
                func_tags = getattr(func, "tags", ())
                for tag in func_tags:
                    if tag not in tags:
                        tags[tag] = tag_lookup.get(tag, {"name": tag})

                request_body = parse_request(func)

                operation_id = camelize(f"{name}", False)
                func_tag = getattr(func, "tags", [])
                parameters = parse_params(func, parameters[:], self.models)
                responses = parse_resp(func, self.config.VALIDATION_ERROR_CODE)
                if (
                    path in self.class_view_apispec
                    and method.lower() in self.class_view_apispec[path]
                ):
                    # flask class view
                    summary = self.class_view_apispec[path][method.lower()]["summary"]
                    operation_id = camelize(method.lower() + name, False)
                    desc = self.class_view_apispec[path][method.lower()]["description"]
                    func_tag = self.class_view_apispec[path][method.lower()]["tags"]
                    query_parameters = self.class_view_apispec[path][method.lower()]["parameters"]
                    path_parameters = [param for param in parameters if param["in"] == "path"]
                    parameters = path_parameters + query_parameters
                    responses = self.class_view_apispec[path][method.lower()]["responses"]
                    request_body = self.class_view_apispec[path][method.lower()].get(
                        "requestBody", None
                    )
                    publish = self.class_view_apispec[path][method.lower()]["publish"]
                    if self.config.MODE == "publish_only" and not publish:
                        continue
                else:
                    # flask function view
                    if self.bypass_unpublish(func):
                        continue

                if path not in routes:
                    routes[path] = dict()
                routes[path][method.lower()] = {
                    "summary": summary or f"{name} <{method}>",
                    "operationId": operation_id,
                    "description": desc or "",
                    "tags": func_tag,
                    "parameters": parameters,
                    "responses": responses,
                }

                if hasattr(func, "deprecated"):
                    routes[path][method.lower()]["deprecated"] = True

                if request_body:
                    routes[path][method.lower()]["requestBody"] = self._parse_request_body(
                        request_body
                    )

        spec = {
            "openapi": self.config.OPENAPI_VERSION,
            "info": {
                **self.config.INFO,
                **{"title": self.config.TITLE, "version": self.config.VERSION,},
            },
            "tags": list(tags.values()),
            "paths": {**routes},
            "components": {"schemas": {**self._get_model_definitions()}},
        }

        if self.config.SECURITY:
            spec["security"] = self.config.SECURITY

        if self.config.SECURITY_SCHEMES:
            spec["components"]["securitySchemes"] = self.config.SECURITY_SCHEMES

        if self.config.SERVERS:
            spec["servers"] = self.config.SERVERS

        if self.config.EXTRA_FIELDS:
            for k, v in self.config.EXTRA_FIELDS.items():
                spec[k] = v

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
        return cast(Mapping[str, Any], nested_alter(result, "$ref", _move_schema_reference))

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
                    definitions[key] = self._get_open_api_schema(value)
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
            return {"content": {content_type: {"schema": self._get_open_api_schema(schema)}}}
        else:
            return request_body

    def register_class_view_apidoc(self, target):
        endpoint = target.__name__
        rules = self.app.url_map._rules_by_endpoint[endpoint]
        for rule in rules:
            endpoint = rule.endpoint
            rule_string = rule.rule.replace("<", "{").replace(">", "}")
            self.class_view_apispec[rule_string] = self.class_view_api_info[endpoint]
