import gzip
import json
import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

from flask import (
    Flask,
    abort,
    jsonify,
    make_response,
    request,
)
from flask import (
    Request as FlaskRequest,
)
from flask import (
    Response as FlaskResponse,
)
from pydantic import ValidationError, v1
from werkzeug.routing import Rule, parse_converter_args

from .config import Config, OperationIdType
from .types import BaseModelUnion, RequestBase, ResponseBase
from .utils import load_model_schema, parse_multi_dict, parse_rule

if TYPE_CHECKING:
    from werkzeug.datastructures import Headers


@dataclass
class Context:
    query: BaseModelUnion | None
    body: BaseModelUnion | None
    headers: BaseModelUnion | None
    cookies: BaseModelUnion | None


class FlaskBackend:
    app: Flask

    def __init__(self, validator: Any) -> None:
        self.validator = validator
        self.config: Config = validator.config
        self.logger: logging.Logger = logging.getLogger(__name__)

    def find_routes(self, app: Flask) -> Iterator[Rule]:
        openapi_paths = [f"/{self.config.PATH}"]
        for blueprint in app.blueprints.values():
            openapi_paths.append(f"{blueprint.url_prefix}/{self.config.PATH}")
        for rule in app.url_map.iter_rules():
            if any(str(rule).startswith(path) for path in (*openapi_paths, "/static")):
                continue
            yield rule

    def bypass(self, func: Callable, method: str) -> bool:
        if method in ["HEAD", "OPTIONS"]:
            return True
        return False

    def parse_func(self, app: Flask, route: Rule) -> Iterator[tuple[str, Callable]]:
        func = app.view_functions[route.endpoint]
        if route.methods:
            for method in route.methods:
                yield method, func

    def get_operation_id(self, route: Rule, method: str, func: Callable) -> str:
        if self.config.OPERATION_ID_TYPE == OperationIdType.endpoint_name_short:
            return cast("str", route.endpoint).split(".")[-1]
        elif self.config.OPERATION_ID_TYPE == OperationIdType.endpoint_name_full:
            return cast("str", route.endpoint)

        return func.__name__

    def parse_path(self, route: Rule) -> tuple[str, list[dict[str, Any]]]:
        subs = []
        parameters: list[dict[str, Any]] = []

        for converter, arguments, variable in parse_rule(route):
            if converter is None:
                subs.append(variable)
                continue
            subs.append(f"{{{variable}}}")

            args: Iterable[Any] = []
            kwargs: dict[str, Any] = {}

            if arguments:
                args, kwargs = parse_converter_args(arguments)

            schema = None
            # See: https://werkzeug.palletsprojects.com/en/2.3.x/routing/#built-in-converters
            if converter == "any":
                schema = {
                    "type": "string",
                    "enum": list(args),
                }
            elif converter == "int":
                schema = {
                    "type": "integer",
                    "format": "int32",
                }
                if "max" in kwargs:
                    schema["maximum"] = kwargs["max"]
                if "min" in kwargs:
                    schema["minimum"] = kwargs["min"]
            elif converter == "float":
                schema = {
                    "type": "number",
                    "format": "float",
                }
            elif converter == "uuid":
                schema = {
                    "type": "string",
                    "format": "uuid",
                }
            elif converter == "path":
                schema = {
                    "type": "string",
                    "format": "path",
                }
            elif converter == "string":
                schema = {
                    "type": "string",
                }
                if "length" in kwargs:
                    schema["length"] = kwargs["length"]
                if "maxlength" in kwargs:
                    schema["maxLength"] = kwargs["maxlength"]
                if "minlength" in kwargs:
                    schema["minLength"] = kwargs["minlength"]
            elif converter == "default":
                schema = {"type": "string"}
            else:
                schema = _parse_custom_url_converter(converter, self.app) or {"type": "string"}

            parameters.append(
                {
                    "name": variable,
                    "in": "path",
                    "required": True,
                    "schema": schema,
                }
            )

        return "".join(subs), parameters

    def request_validation(
        self,
        request: FlaskRequest,
        query: type[BaseModelUnion] | None,
        body: RequestBase | None,
        headers: type[BaseModelUnion] | None,
        cookies: type[BaseModelUnion] | None,
    ) -> None:
        raw_query = request.args or None
        if raw_query is not None:
            req_query = parse_multi_dict(raw_query)
        else:
            req_query = {}
        if request.content_type and "application/json" in request.content_type:
            if request.content_encoding and "gzip" in request.content_encoding:
                raw_body = gzip.decompress(request.stream.read()).decode(encoding="utf-8")
                parsed_body = json.loads(raw_body)
            else:
                parsed_body = request.get_json(silent=True) or {}
        elif request.content_type and "multipart/form-data" in request.content_type:
            # It's possible there is a binary json object in the files - iterate through and find it
            parsed_body = {}
            for key, value in request.files.items():
                if value.mimetype == "application/json":
                    parsed_body[key] = json.loads(value.stream.read().decode(encoding="utf-8"))
            # Finally, find any JSON objects in the form and add them to the body
            parsed_body.update(parse_multi_dict(request.form) or {})
        else:
            parsed_body = request.get_data() or {}

        req_headers: Headers = request.headers
        req_cookies: Mapping[str, str] = request.cookies
        body_model = getattr(body, "model", None) if body else None
        request.context = Context(  # type: ignore[attr-defined]
            query=load_model_schema(query, req_query) if query is not None else None,
            body=load_model_schema(body_model, parsed_body) if body_model else None,
            headers=load_model_schema(headers, dict(req_headers)) if headers else None,
            cookies=load_model_schema(cookies, dict(req_cookies)) if cookies else None,
        )

    def validate(
        self,
        func: Callable,
        query: type[BaseModelUnion] | None,
        body: RequestBase | None,
        headers: type[BaseModelUnion] | None,
        cookies: type[BaseModelUnion] | None,
        resp: ResponseBase | None,
        before: Callable,
        after: Callable,
        *args: list[Any],
        **kwargs: Mapping[str, Any],
    ) -> FlaskResponse:
        response, req_validation_error, resp_validation_error = None, None, None
        try:
            self.request_validation(request, query, body, headers, cookies)
        except (ValidationError, v1.ValidationError) as err:
            req_validation_error = err
            response = make_response(
                jsonify(json.loads(err.json())), self.config.VALIDATION_ERROR_CODE
            )

        before(request, response, req_validation_error, None)
        if req_validation_error:
            abort(response)  # type: ignore

        response = make_response(func(*args, **kwargs))

        if resp and resp.has_model() and getattr(resp, "validate", False):
            model = resp.find_model(response.status_code)
            if model:
                try:
                    load_model_schema(model, response.get_json())
                except (ValidationError, v1.ValidationError) as err:
                    resp_validation_error = err
                    response = make_response(jsonify({"message": "response validation error"}), 500)

        after(request, response, resp_validation_error, None)

        return response


def _parse_custom_url_converter(converter: str, app: Flask) -> dict[str, Any] | None:
    """Attempt derive a schema from a custom URL converter."""
    try:
        converter_cls = app.url_map.converters[converter]
        import inspect

        signature = inspect.signature(converter_cls.to_python)
        return_type = signature.return_annotation
        if issubclass(return_type, Enum):
            return {
                "type": "string",
                "enum": [e.value for e in return_type],
            }
    except (KeyError, AttributeError):
        pass
    return None
