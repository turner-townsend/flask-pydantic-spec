from enum import Enum
import re
from typing import Optional, List, Any, Mapping

import pytest
from flask import Flask, Blueprint
from openapi_spec_validator import OpenAPIV31SpecValidator
from pydantic import BaseModel, StrictFloat, Field, RootModel

from flask_pydantic_spec import Response
from flask_pydantic_spec.types import FileResponse, Request, MultipartFormRequest
from flask_pydantic_spec import FlaskPydanticSpec
from flask_pydantic_spec.config import Config
from flask_pydantic_spec.utils import get_model_name

from tests.common import ExampleConverter, UnknownConverter


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


@pytest.fixture
def empty_app():
    return Flask(__name__)


@pytest.fixture
def app_name():
    return "flask"


@pytest.fixture
def blueprint_name():
    return "blueprint"


@pytest.fixture
def empty_blueprint(blueprint_name):
    return Blueprint(blueprint_name, __name__, url_prefix="/blueprint")


@pytest.fixture
def api() -> FlaskPydanticSpec:
    return FlaskPydanticSpec(
        "flask",
        tags=[{"name": "lone", "description": "a lone api"}],
        validation_error_code=400,
    )


@pytest.fixture
def bp_api(api: FlaskPydanticSpec, empty_blueprint: Blueprint) -> FlaskPydanticSpec:
    return api.for_blueprint(
        empty_blueprint,
        tags=[{"name": "lone", "description": "a lone api"}],
    )


def test_spectree_init():
    spec = FlaskPydanticSpec(path="docs")
    conf = Config()

    assert spec.config.TITLE == conf.TITLE
    assert spec.config.PATH == "docs"


def test_register(app_name, empty_app, empty_blueprint):
    api = FlaskPydanticSpec(app_name)
    api.register(empty_app)
    blueprint_api = FlaskPydanticSpec("blueprint_api")

    blueprint_api.register(empty_blueprint)
    empty_app.register_blueprint(empty_blueprint)


def test_spec_generate(app_name, empty_app, empty_blueprint):
    api = FlaskPydanticSpec(app_name)
    api.register(empty_app)

    bp_spec = api.for_blueprint(
        empty_blueprint,
        title=empty_blueprint.name,
        info={"title": "override", "description": "blueprint level description"},
    )
    empty_app.register_blueprint(empty_blueprint)

    spec = bp_spec.spec

    assert spec["info"]["title"] == empty_blueprint.name
    assert spec["info"]["description"] == "blueprint level description"
    assert spec["paths"] == {}
    assert spec["tags"] == []


@pytest.fixture
def app(api: FlaskPydanticSpec, empty_blueprint: Blueprint, bp_api: FlaskPydanticSpec) -> Flask:
    app = Flask(__name__)
    app.url_map.converters["example"] = ExampleConverter
    app.url_map.converters["unknown"] = UnknownConverter

    @empty_blueprint.route("/foo")
    @bp_api.validate(resp=Response(HTTP_200=ExampleModel))
    def foo():
        pass

    @empty_blueprint.route("/lone", methods=["POST"])
    @bp_api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=ExampleNestedList, HTTP_400=ExampleNestedModel),
        tags=["lone"],
        deprecated=True,
    )
    def lone_post():
        pass

    @empty_blueprint.route("/lone", methods=["PATCH"])
    @bp_api.validate(
        body=Request(ExampleModel),
        resp=Response(HTTP_200=List[ExampleModel], HTTP_400=ExampleNestedModel),
        tags=["lone"],
    )
    def lone_patch():
        pass

    @empty_blueprint.route("/query", methods=["GET"])
    @bp_api.validate(query=ExampleQuery, resp=Response(HTTP_200=List[ExampleModel]))
    def get_query():
        pass

    @empty_blueprint.route("/file")
    @bp_api.validate(resp=FileResponse())
    def get_file():
        pass

    @empty_blueprint.route("/file", methods=["POST"])
    @bp_api.validate(
        body=Request(content_type="application/octet-stream"),
        resp=FileResponse(),
    )
    def post_file():
        pass

    @empty_blueprint.route("/multipart-file", methods=["POST"])
    @bp_api.validate(body=MultipartFormRequest(ExampleModel), resp=Response(HTTP_200=ExampleModel))
    def post_multipart_form():
        pass

    @empty_blueprint.route("/enum/<example:example>", methods=["GET"])
    @bp_api.validate(resp=Response(HTTP_200=ExampleModel))
    def get_enum(example):
        pass

    app.register_blueprint(empty_blueprint)
    return app


@pytest.fixture
def registered_blueprint_spec(
    app: Flask, api: FlaskPydanticSpec, bp_api: FlaskPydanticSpec
) -> Mapping[str, Any]:
    api.register(app)
    return bp_api.spec


def test_two_endpoints_with_the_same_path(registered_blueprint_spec: dict[str, Any]) -> None:
    http_methods = list(registered_blueprint_spec["paths"]["/blueprint/lone"].keys())
    http_methods.sort()
    assert http_methods == ["patch", "post"]


def test_valid_openapi_spec(registered_blueprint_spec: dict[str, Any]) -> None:
    assert OpenAPIV31SpecValidator(registered_blueprint_spec).is_valid()


def test_openapi_tags(registered_blueprint_spec: dict[str, Any]) -> None:
    assert registered_blueprint_spec["tags"][0]["name"] == "lone"
    assert registered_blueprint_spec["tags"][0]["description"] == "a lone api"


def test_openapi_deprecated(registered_blueprint_spec: dict[str, Any]) -> None:
    assert registered_blueprint_spec["paths"]["/blueprint/lone"]["post"]["deprecated"] is True
    assert "deprecated" not in registered_blueprint_spec["paths"]["/blueprint/lone"]["patch"]


def test_flat_array_schemas(registered_blueprint_spec: dict[str, Any]) -> None:
    assert (
        registered_blueprint_spec["components"]["schemas"][get_model_name(ExampleNestedList)].get(
            "items"
        )
        is not None
    )


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
def test_url_converters(route: str, schema: dict, empty_blueprint: Blueprint) -> None:
    app = Flask(__name__)
    app.url_map.converters["example"] = ExampleConverter
    app.url_map.converters["unknown"] = UnknownConverter

    api = FlaskPydanticSpec(
        "flask",
        tags=[{"name": "lone", "description": "a lone api"}],
        validation_error_code=400,
    )
    bp_api = api.for_blueprint(empty_blueprint)

    @empty_blueprint.get(route)
    @bp_api.validate(resp=Response(HTTP_200=None))
    def get_with_converter(example):
        pass

    app.register_blueprint(empty_blueprint)
    api.register(app)

    spec = bp_api.spec

    spec_route = re.sub(r"<.*:(.*)>", r"{\1}", route)
    spec_route = f"/blueprint{spec_route}"

    assert spec["paths"][spec_route]["get"]["parameters"][0]["schema"] == schema


def test_flat_array_schema_from_python_list_type(registered_blueprint_spec: dict[str, Any]) -> None:
    schema_spec = registered_blueprint_spec["paths"]["/blueprint/lone"]["patch"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"]

    assert (
        schema_spec["type"] == "array"
        and schema_spec["items"]["$ref"] == "#/components/schemas/ExampleModel"
    )
