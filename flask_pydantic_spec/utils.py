import inspect
import json
import logging
import re
from collections import defaultdict
from json import JSONDecodeError

from typing import (
    Callable,
    Mapping,
    Any,
    Tuple,
    Optional,
    List,
    Dict,
    Iterable,
    Type,
    cast,
    Union,
)

from nested_lookup import nested_alter
from werkzeug.datastructures import MultiDict
from pydantic import BaseModel
from werkzeug.routing import Rule

from .types import Response, RequestBase, Request

logger = logging.getLogger(__name__)


def _move_schema_reference(reference: str) -> str:
    if "/definitions" in reference:
        return f"#/components/schemas/{reference.split('/definitions/')[-1]}"
    return reference


def _get_ref(model: Type[BaseModel]) -> Mapping[str, Any]:
    return {"$ref": f"#/components/schemas/{model.__name__}"}


def _validate_property(property: Mapping[str, Any]) -> Dict[str, Any]:
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


def get_open_api_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    """
    Convert a Pydantic model into an OpenAPI compliant schema object.
    """
    result = {}
    for key, value in schema.items():
        if key == "properties":
            result[key] = _validate_property(value)
        else:
            result[key] = value
    return cast(Mapping[str, Any], nested_alter(result, "$ref", _move_schema_reference))


def parse_comments(func: Callable) -> Tuple[Optional[str], Optional[str]]:
    """
    parse function comments

    First line of comments will be saved as summary, and the rest
    will be saved as description.
    """
    doc = inspect.getdoc(func)
    if doc is None:
        return None, None
    docs = doc.split("\n", 1)
    if len(docs) == 1:
        return docs[0], None
    return docs[0], docs[1].strip()


def parse_request(func: Callable) -> Mapping[str, Any]:
    """
    Generate spec from body parameter on the view function validation decorator
    """
    if hasattr(func, "body"):
        request_body = getattr(func, "body")
        if isinstance(request_body, RequestBase):
            result: Mapping[str, Any] = request_body.generate_spec()
        elif issubclass(request_body, BaseModel):
            result = Request(request_body).generate_spec()
        else:
            result = {}
        return result
    return {}


def _get_param(
    model: Type[BaseModel], key: str, inline: bool
) -> Union[List[Mapping[str, Any]], Mapping[str, Any]]:
    """
    Parses a model as a parameter object, either as an inlined parameter object (where the schema is defined within
    the operation) or as a reference to the Parameter in the Spec, which will reference the Schema for the Parameter.
    """
    model_schema = get_open_api_schema(model.schema())
    if not inline:
        return {
            "name": model_schema["title"],
            "in": key,
            "schema": _get_ref(model),
        }
    return [
        {
            "name": name,
            "in": key,
            "schema": schema,
            "required": name in model_schema.get("required", {}),
        }
        for name, schema in model_schema["properties"].items()
    ]


def parse_params(
    func: Callable, inline: bool = True
) -> Mapping[str, Union[List[Mapping[str, Any]], Mapping[str, Any]]]:
    """
    get spec for (query, headers, cookies)
    """
    result = {}
    if hasattr(func, "query"):
        model = getattr(func, "query")
        result["query"] = {model.__name__: _get_param(model, "query", inline)}

    if hasattr(func, "headers"):
        model = getattr(func, "headers")
        result["headers"] = {model.__name__: _get_param(model, "header", inline)}

    if hasattr(func, "cookies"):
        model = getattr(func, "cookies")
        result["cookies"] = {model.__name__: _get_param(model, "cookie", inline)}

    return result


def parse_resp(func: Callable, code: int) -> Mapping[str, Mapping[str, Any]]:
    """
    get the response spec

    If this function does not have explicit ``resp`` but have other models,
    a ``Validation Error`` will be appended to the response spec. Since
    this may be triggered in the validation step.
    """
    responses: Dict[str, Any] = {}
    if hasattr(func, "resp"):
        response = getattr(func, "resp")
        if response:
            responses = response.generate_spec()

    if str(code) not in responses and has_model(func):
        responses[str(code)] = {"description": "Validation Error"}

    return responses


def has_model(func: Callable) -> bool:
    """
    return True if this function have ``pydantic.BaseModel``
    """
    if any(hasattr(func, x) for x in ("query", "json", "headers")):
        return True

    if hasattr(func, "resp") and getattr(func, "resp").has_model():
        return True

    return False


def parse_name(func: Callable) -> str:
    """
    the func can be

        * undecorated functions
        * decorated functions
        * decorated class methods
    """
    return func.__name__


def default_before_handler(
    req: Request, resp: Response, req_validation_error: Any, instance: BaseModel
) -> None:
    """
    default handler called before the endpoint function after the request validation

    :param req: request provided by the web framework
    :param resp: response generated by Flask_Pydantic_Spec that will be returned
        if the validation error is not None
    :param req_validation_error: request validation error
    :param instance: class instance if the endpoint function is a class method
    """
    if req_validation_error:
        logger.info(
            "Validation Error",
            extra={
                "spectree_model": req_validation_error.model.__name__,
                "spectree_validation": req_validation_error.errors(),
            },
        )


def default_after_handler(
    req: Request,
    resp: Response,
    resp_validation_error: Any,
    instance: BaseModel,
) -> None:
    """
    default handler called after the response validation

    :param req: request provided by the web framework
    :param resp: response from the endpoint function (if there is no validation error)
        or response validation error
    :param resp_validation_error: response validation error
    :param instance: class instance if the endpoint function is a class method
    """
    if resp_validation_error:
        logger.info(
            "500 Response Validation Error",
            extra={
                "spectree_model": resp_validation_error.model.__name__,
                "spectree_validation": resp_validation_error.errors(),
            },
        )


def parse_multi_dict(input: MultiDict) -> Dict[str, Any]:
    result = {}
    for key, value in input.to_dict(flat=False).items():
        if len(value) == 1:
            try:
                value_to_use = json.loads(value[0])
            except (TypeError, JSONDecodeError):
                value_to_use = value[0]
        else:
            value_to_use = value
        result[key] = value_to_use
    return result


RE_PARSE_RULE = re.compile(
    r"""
    (?P<static>[^<]*)                           # static rule data
    <
    (?:
        (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)   # converter name
        (?:\((?P<args>.*?)\))?                  # converter arguments
        \:                                      # variable delimiter
    )?
    (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)        # variable name
    >
    """,
    re.VERBOSE,
)


def parse_rule(
    rule: Rule,
) -> Iterable[Tuple[Optional[str], Optional[str], str]]:
    """
    Parse a rule and return it as generator. Each iteration yields tuples in the form
    ``(converter, arguments, variable)``.
    If the converter is `None` it's a static url part, otherwise it's a dynamic one.
    Note: This originally lived in werkzeug.routing.parse_rule until it was removed in werkzeug 2.2.0.
    TODO - cgearing - do we really need this?
    """
    rule_str = str(rule)
    pos = 0
    end = len(rule_str)
    do_match = RE_PARSE_RULE.match
    used_names = set()
    while pos < end:
        m = do_match(rule_str, pos)
        if m is None:
            break
        data = m.groupdict()
        if data["static"]:
            yield None, None, data["static"]
        variable = data["variable"]
        converter = data["converter"] or "default"
        if variable in used_names:
            raise ValueError(f"variable name {variable!r} used twice.")
        used_names.add(variable)
        yield converter, data["args"] or None, variable
        pos = m.end()
    if pos < end:
        remaining = rule_str[pos:]
        if ">" in remaining or "<" in remaining:
            raise ValueError(f"malformed url rule: {rule_str!r}")
        yield None, None, remaining
