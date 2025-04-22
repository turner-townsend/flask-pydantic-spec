from enum import Enum
import re
from typing import Any, Optional, List

import pytest
from flask import Flask
from openapi_spec_validator import OpenAPIV31SpecValidator
from pydantic import BaseModel, StrictFloat, Field, RootModel
from pydantic import v1

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


class ExampleNestedList(RootModel):
    root: List[ExampleModel]


class ExampleNestedModel(BaseModel):
    example: ExampleModel


class ExampleDeepNestedModel(BaseModel):
    data: List["ExampleModel"]


class ExampleV1Model(v1.BaseModel):
    name: str = v1.Field(strip_whitespace=True)
    age: int
    height: StrictFloat


class ExampleV1Query(v1.BaseModel):
    query: str
    type: Optional[TypeEnum] = None


class ExampleV1NestedList(v1.BaseModel):
    __root__: List[ExampleV1Model]


class ExampleV1NestedModel(v1.BaseModel):
    example: ExampleV1Model


class ExampleV1DeepNestedModel(v1.BaseModel):
    data: List["ExampleV1Model"]


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

    @app.get("/foo")
    @api.validate(resp=Response(HTTP_200=ExampleModel))
    def foo():
        pass

    @app.post("/lone")
    @api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=ExampleNestedList, HTTP_400=ExampleNestedModel),
        tags=["lone"],
        deprecated=True,
    )
    def lone_post():
        pass

    @app.patch("/lone")
    @api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=List[ExampleModel], HTTP_400=ExampleNestedModel),
        tags=["lone"],
    )
    def lone_patch():
        pass

    @app.get("/query")
    @api.validate(query=ExampleQuery, resp=Response(HTTP_200=List[ExampleModel]))
    def get_query():
        pass

    @app.get("/file")
    @api.validate(resp=FileResponse())
    def get_file():
        pass

    @app.post("/file")
    @api.validate(
        body=Request(content_type="application/octet-stream"),
        resp=FileResponse(),
    )
    def post_file():
        pass

    @app.post("/multipart-file")
    @api.validate(body=MultipartFormRequest(ExampleModel), resp=Response(HTTP_200=ExampleModel))
    def post_multipart_form():
        pass

    @app.get("/enum/<example:example>")
    @api.validate(resp=Response(HTTP_200=ExampleModel))
    def get_enum(example):
        pass

    @app.get("/v1/foo")
    @api.validate(resp=Response(HTTP_200=ExampleV1Model))
    def foo_v1():
        pass

    @app.post("/v1/lone")
    @api.validate(
        body=Request(ExampleV1Model),
        resp=Response(HTTP_200=ExampleV1NestedList, HTTP_400=ExampleV1NestedModel),
        tags=["lone"],
        deprecated=True,
    )
    def lone_post_v1():
        pass

    @app.patch("/v1/lone")
    @api.validate(
        body=Request(ExampleV1Model),
        resp=Response(HTTP_200=List[ExampleV1Model], HTTP_400=ExampleV1NestedModel),
        tags=["lone"],
    )
    def lone_patch_v1():
        pass

    @app.get("/v1/query")
    @api.validate(query=ExampleV1Query, resp=Response(HTTP_200=List[ExampleV1Model]))
    def get_query_v1():
        pass

    @app.post("/v1/multipart-file")
    @api.validate(body=MultipartFormRequest(ExampleV1Model), resp=Response(HTTP_200=ExampleV1Model))
    def post_multipart_form_v1():
        pass

    @app.get("/v1/enum/<example:example>")
    @api.validate(resp=Response(HTTP_200=ExampleV1Model))
    def get_enum_v1(example):
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


# TODO: add tests for v1 schemas
def strip_v1(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: strip_v1(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [strip_v1(item) for item in data]
    elif isinstance(data, str):
        return data.replace("V1", "").replace("_v1", "")
    else:
        return data


@pytest.mark.parametrize(
    ("route", "method"),
    [
        ("/foo", "get"),
        ("/lone", "post"),
        ("/lone", "patch"),
        ("/multipart-file", "post"),
        ("/enum/{example}", "get"),
    ],
)
def test_v1_routes_match_v2(app: Flask, api: FlaskPydanticSpec, route: str, method: str):
    api.register(app)
    spec = api.spec
    v1_route = f"/v1{route}"

    v1_spec = spec["paths"][v1_route][method]
    v2_spec = spec["paths"][route][method]

    assert strip_v1(v1_spec) == v2_spec


@pytest.mark.parametrize(
    ("route", "method"),
    [
        ("/query", "get"),
    ],
)
def test_v1_routes_with_nullable_match(app: Flask, api: FlaskPydanticSpec, route: str, method: str):
    api.register(app)
    spec = api.spec
    v1_route = f"/v1{route}"

    v1_spec = spec["paths"][v1_route][method]
    v2_spec = spec["paths"][route][method]

    v1_query_type = v1_spec["parameters"][1].pop("schema")
    v2_query_type = v2_spec["parameters"][1].pop("schema")

    assert strip_v1(v1_spec) == v2_spec
    # Pydantic v1 was incorrectly implemented
    assert v1_query_type == {"$ref": "#/components/schemas/TypeEnum"}
    assert v2_query_type == {
        "anyOf": [{"$ref": "#/components/schemas/TypeEnum"}, {"type": "null"}],
        "default": None,
    }
