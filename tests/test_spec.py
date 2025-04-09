from enum import Enum
import re
from typing import Optional, List

import pytest
from flask import Flask
from openapi_spec_validator import openapi_v31_spec_validator, OpenAPIV31SpecValidator
from pydantic import BaseModel, StrictFloat, Field, RootModel

from flask_pydantic_spec import Response
from flask_pydantic_spec.types import FileResponse, Request, MultipartFormRequest
from flask_pydantic_spec import FlaskPydanticSpec
from flask_pydantic_spec.config import Config
from flask_pydantic_spec.utils import get_model_name

from .common import ExampleConverter, UnknownConverter


class ExampleModel(BaseModel):
    name: str = Field(json_schema_extra={"strip_whitespace": True})
    age: int
    height: StrictFloat


class TypeEnum(str, Enum):
    foo = "foo"
    bar = "bar"


class ExampleQuery(BaseModel):
    query: str
    type: Optional[TypeEnum] = None


ExampleNestedList = RootModel[List[ExampleModel]]


class ExampleNestedModel(BaseModel):
    example: ExampleModel


class ExampleDeepNestedModel(BaseModel):
    data: List["ExampleModel"]


def backend_app():
    return [
        ("flask", Flask(__name__)),
    ]


@pytest.fixture
def empty_app():
    return Flask(__name__)


@pytest.fixture
def name():
    return "flask"


@pytest.fixture
def api(name) -> FlaskPydanticSpec:
    return FlaskPydanticSpec(
        name,
        tags=[{"name": "lone", "description": "a lone api"}],
        validation_error_code=400,
    )


def test_spectree_init():
    spec = FlaskPydanticSpec(path="docs")
    conf = Config()

    assert spec.config.TITLE == conf.TITLE
    assert spec.config.PATH == "docs"


def test_register(name, empty_app):
    api = FlaskPydanticSpec(name)
    api.register(empty_app)


def test_spec_generate(name, empty_app):
    api = FlaskPydanticSpec(
        name,
        app=empty_app,
        title=f"{name}",
        info={"title": "override", "description": "api level description"},
        tags=[{"name": "lone", "description": "a lone api"}],
    )
    spec = api.spec

    assert spec["info"]["title"] == name
    assert spec["info"]["description"] == "api level description"
    assert spec["paths"] == {}
    assert spec["tags"] == []


@pytest.fixture
def app(api: FlaskPydanticSpec) -> Flask:
    app = Flask(__name__)
    app.url_map.converters["example"] = ExampleConverter
    app.url_map.converters["unknown"] = UnknownConverter

    @app.route("/foo")
    @api.validate(resp=Response(HTTP_200=ExampleModel))
    def foo():
        pass

    @app.route("/lone", methods=["POST"])
    @api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=ExampleNestedList, HTTP_400=ExampleNestedModel),
        tags=["lone"],
        deprecated=True,
    )
    def lone_post():
        pass

    @app.route("/lone", methods=["PATCH"])
    @api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=List[ExampleModel], HTTP_400=ExampleNestedModel),
        tags=["lone"],
    )
    def lone_patch():
        pass

    @app.route("/query", methods=["GET"])
    @api.validate(query=ExampleQuery, resp=Response(HTTP_200=List[ExampleModel]))
    def get_query():
        pass

    @app.route("/file")
    @api.validate(resp=FileResponse())
    def get_file():
        pass

    @app.route("/file", methods=["POST"])
    @api.validate(
        body=Request(content_type="application/octet-stream"),
        resp=FileResponse(),
    )
    def post_file():
        pass

    @app.route("/multipart-file", methods=["POST"])
    @api.validate(body=MultipartFormRequest(ExampleModel), resp=Response(HTTP_200=ExampleModel))
    def post_multipart_form():
        pass

    @app.route("/enum/<example:example>", methods=["GET"])
    @api.validate(resp=Response(HTTP_200=ExampleModel))
    def get_enum(example):
        pass

    return app


def test_two_endpoints_with_the_same_path(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec

    http_methods = list(spec["paths"]["/lone"].keys())
    http_methods.sort()
    assert http_methods == ["patch", "post"]


def test_valid_openapi_spec(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec

    assert OpenAPIV31SpecValidator(spec).is_valid()


def test_openapi_tags(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec

    assert spec["tags"][0]["name"] == "lone"
    assert spec["tags"][0]["description"] == "a lone api"


def test_openapi_deprecated(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec

    assert spec["paths"]["/lone"]["post"]["deprecated"] is True
    assert "deprecated" not in spec["paths"]["/lone"]["patch"]


def test_flat_array_schemas(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec
    assert spec["components"]["schemas"][get_model_name(ExampleNestedList)].get("items") is not None


@pytest.mark.parametrize(
    ("route", "schema"),
    [
        pytest.param(
            "/convert/<any(a, b, c):example>",
            {"type": "string", "enum": ["a", "b", "c"]},
            id="any",
        ),
        pytest.param(
            "/convert/<int(min=1, max=5):example>",
            {"type": "integer", "format": "int32", "minimum": 1, "maximum": 5},
            id="int",
        ),
        pytest.param(
            "/convert/<uuid:example>",
            {"type": "string", "format": "uuid"},
            id="uuid",
        ),
        pytest.param(
            "/convert/<float:example>",
            {"type": "number", "format": "float"},
            id="float",
        ),
        pytest.param(
            "/convert/<path:example>",
            {"type": "string", "format": "path"},
            id="path",
        ),
        pytest.param(
            "/convert/<string(length=5):example>",
            {"type": "string", "length": 5},
            id="string-with-length",
        ),
        pytest.param(
            "/convert/<string(maxlength=5):example>",
            {"type": "string", "maxLength": 5},
            id="string-with-max-length",
        ),
        pytest.param(
            "/convert/<unknown:example>",
            {"type": "string"},
            id="custom-unknown",
        ),
        pytest.param(
            "/convert/<example:example>",
            {"type": "string", "enum": ["one", "two"]},
            id="custom-enum",
        ),
    ],
)
def test_url_converters(route, schema, app: Flask, api: FlaskPydanticSpec):
    @app.get(route)
    @api.validate(resp=Response(HTTP_200=None))
    def get_with_converter(example):
        pass

    api.register(app)

    spec = api.spec

    spec_route = re.sub(r"<.*:(.*)>", r"{\1}", route)

    assert spec["paths"][spec_route]["get"]["parameters"][0]["schema"] == schema


def test_flat_array_schema_from_python_list_type(app: Flask, api: FlaskPydanticSpec):
    api.register(app)
    spec = api.spec

    schema_spec = spec["paths"]["/lone"]["patch"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert (
        schema_spec["type"] == "array"
        and schema_spec["items"]["$ref"] == "#/components/schemas/ExampleModel"
    )
