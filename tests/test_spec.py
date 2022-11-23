from enum import Enum
from typing import Optional

import pytest
from flask import Flask
from typing import List
from openapi_spec_validator import validate_spec, openapi_v30_spec_validator
from pydantic import BaseModel, StrictFloat, Field

from flask_pydantic_spec import Response
from flask_pydantic_spec.types import FileResponse, Request, MultipartFormRequest
from flask_pydantic_spec import FlaskPydanticSpec
from flask_pydantic_spec.config import Config

from .common import get_paths


class ExampleModel(BaseModel):
    name: str = Field(strip_whitespace=True)
    age: int
    height: StrictFloat


class TypeEnum(str, Enum):
    foo = "foo"
    bar = "bar"


class ExampleQuery(BaseModel):
    query: str
    type: Optional[TypeEnum]


class ExampleNestedList(BaseModel):
    __root__: List[ExampleModel]


class ExampleNestedModel(BaseModel):
    example: ExampleModel


class ExampleDeepNestedModel(BaseModel):
    data: List["ExampleModel"]


def backend_app():
    return [
        ("flask", Flask(__name__)),
    ]


def test_spectree_init():
    spec = FlaskPydanticSpec(path="docs")
    conf = Config()

    assert spec.config.TITLE == conf.TITLE
    assert spec.config.PATH == "docs"


@pytest.mark.parametrize("name, app", backend_app())
def test_register(name, app):
    api = FlaskPydanticSpec(name)
    api.register(app)


@pytest.mark.parametrize("name, app", backend_app())
def test_spec_generate(name, app):
    api = FlaskPydanticSpec(
        name,
        app=app,
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
def api() -> FlaskPydanticSpec:
    return FlaskPydanticSpec(
        "flask",
        tags=[{"name": "lone", "description": "a lone api"}],
        validation_error_code=400,
    )


@pytest.fixture
def api_strict() -> FlaskPydanticSpec:
    return FlaskPydanticSpec("flask", mode="strict")


@pytest.fixture
def api_greedy() -> FlaskPydanticSpec:
    return FlaskPydanticSpec("flask", mode="greedy")


@pytest.fixture
def app(api: api) -> Flask:
    _app = Flask(__name__)

    @_app.get("/lone")
    @api.validate(resp=Response(HTTP_200=ExampleNestedList))
    def lone_get():
        pass

    @_app.post("/lone")
    @api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=ExampleNestedList, HTTP_400=ExampleNestedModel),
        tags=["lone"],
        deprecated=True,
    )
    def lone_post():
        pass

    @_app.get("/query")
    @api.validate(query=ExampleQuery)
    def get_query():
        pass

    @_app.get("/file")
    @api.validate(resp=FileResponse())
    def get_file():
        pass

    @_app.post("/file")
    @api.validate(
        body=Request(content_type="application/octet-stream"),
        resp=Response(HTTP_200=None),
    )
    def post_file():
        pass

    @_app.post("/multipart-file")
    @api.validate(body=MultipartFormRequest(ExampleModel), resp=Response(HTTP_200=ExampleModel))
    def post_multipart_form():
        pass

    return _app


def test_spec_paths(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    assert get_paths(api.spec) == [
        "/file",
        "/lone",
        "/multipart-file",
        "/query",
    ]


def test_api_greedy(app: Flask, api_greedy: FlaskPydanticSpec) -> None:
    api_greedy.register(app)
    assert get_paths(api_greedy.spec) == [
        "/file",
        "/lone",
        "/multipart-file",
        "/query",
    ]


def test_api_strict(app: Flask, api_strict: FlaskPydanticSpec) -> None:
    api_strict.register(app)
    assert get_paths(api_strict.spec) == []


def test_two_endpoints_with_the_same_path(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    spec = api.spec

    http_methods = list(spec["paths"]["/lone"].keys())
    http_methods.sort()
    assert http_methods == ["get", "post"]


def test_valid_openapi_spec(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    spec = api.spec

    validate_spec(spec, validator=openapi_v30_spec_validator)


def test_openapi_tags(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    spec = api.spec

    assert spec["tags"][0]["name"] == "lone"
    assert spec["tags"][0]["description"] == "a lone api"


def test_openapi_deprecated(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    spec = api.spec

    assert spec["paths"]["/lone"]["post"]["deprecated"] == True
    assert "deprecated" not in spec["paths"]["/lone"]["get"]


def test_query_as_reference(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    api.config.INLINE_DEFINITIONS = False
    spec = api.spec
    assert spec["paths"]["/query"]["get"]["parameters"][0] == {
        "$ref": "#/components/parameters/ExampleQuery"
    }
    assert spec["components"]["parameters"]["ExampleQuery"]["schema"] == {
        "$ref": "#/components/schemas/ExampleQuery"
    }
    assert spec["components"]["schemas"]["ExampleQuery"] is not None


def test_valid_spec_with_all_references(app: Flask, api: FlaskPydanticSpec) -> None:
    api.register(app)
    api.config.INLINE_DEFINITIONS = False

    validate_spec(api.spec, validator=openapi_v30_spec_validator)
