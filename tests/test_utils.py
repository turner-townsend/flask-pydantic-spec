import pytest

from flask_pydantic_spec.utils import (
    parse_comments,
    parse_request,
    parse_params,
    parse_resp,
    has_model,
)
from flask_pydantic_spec.spec import FlaskPydanticSpec
from flask_pydantic_spec.types import Response, Request, _parse_code

from .common import DemoModel


api = FlaskPydanticSpec()


def undecorated_func():
    """summary
    description"""
    pass


@api.validate(body=Request(model=DemoModel), resp=Response(HTTP_200=DemoModel))
def demo_func():
    """
    summary

    description"""
    pass


class DemoClass:
    @api.validate(query=DemoModel, resp=Response(HTTP_200=DemoModel))
    def demo_method(self):
        """summary
        description
        """
        pass


demo_class = DemoClass()


def test_comments():
    assert parse_comments(lambda x: x) == (None, None)
    assert parse_comments(undecorated_func) == ("summary", "description")
    assert parse_comments(demo_func) == ("summary", "description")
    assert parse_comments(demo_class.demo_method) == ("summary", "description")


def test_parse_code():
    with pytest.raises(TypeError):
        assert _parse_code(200) == 200

    assert _parse_code("200") is None
    assert _parse_code("HTTP_404") == "404"


def test_has_model():
    assert not has_model(undecorated_func)
    assert has_model(demo_func)
    assert has_model(demo_class.demo_method)


def test_parse_resp():
    assert parse_resp(undecorated_func, 422) == {}
    assert parse_resp(demo_class.demo_method, 422) == {
        "200": {
            "description": "OK",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/DemoModel"}}},
        },
        "422": {"description": "Validation Error"},
    }
    resp_spec = parse_resp(demo_func, 422)
    assert resp_spec["422"]["description"] == "Validation Error"
    assert (
        resp_spec["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DemoModel"
    )

    resp_spec = parse_resp(demo_func, 400)
    assert "422" not in resp_spec
    assert resp_spec["400"]["description"] == "Validation Error"


def test_parse_request():
    assert (
        parse_request(demo_func)["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/DemoModel"
    )
    assert parse_request(demo_class.demo_method) == {}


def test_parse_params():
    models = {"DemoModel": DemoModel.model_json_schema()}
    assert parse_params(demo_func, [], models) == []
    params = parse_params(demo_class.demo_method, [], models)
    assert len(params) == 3
    assert params[0] == {
        "name": "uid",
        "in": "query",
        "required": True,
        "schema": {
            "title": "Uid",
            "type": "integer",
        },
    }
