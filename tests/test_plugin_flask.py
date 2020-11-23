from io import BytesIO
from random import randint
import pytest
import json
from flask import Flask, jsonify, request
from werkzeug.datastructures import FileStorage

from flask_pydantic_spec.types import Response, MultipartFormRequest
from flask_pydantic_spec import FlaskPydanticSpec

from .common import Query, Resp, JSON, Headers, Cookies, DemoModel


def before_handler(req, resp, err, _):
    if err:
        resp.headers["X-Error"] = "Validation Error"


def after_handler(req, resp, err, _):
    resp.headers["X-Validation"] = "Pass"


def api_after_handler(req, resp, err, _):
    resp.headers["X-API"] = "OK"


api = FlaskPydanticSpec(
    "flask", before=before_handler, after=after_handler, title="Test API"
)
app = Flask(__name__)


@app.route("/ping")
@api.validate(headers=Headers, tags=["test", "health"])
def ping():
    """summary
    description"""
    return jsonify(msg="pong")


@app.route("/api/user/<name>", methods=["POST"])
@api.validate(
    query=Query,
    body=JSON,
    cookies=Cookies,
    resp=Response(HTTP_200=Resp, HTTP_401=None),
    tags=["api", "test"],
    after=api_after_handler,
)
def user_score(name):
    score = [randint(0, request.context.body.limit) for _ in range(5)]
    score.sort(
        reverse=request.context.query.order if request.context.query.order else False
    )
    assert request.context.cookies.pub == "abcdefg"
    assert request.cookies["pub"] == "abcdefg"
    return jsonify(name=request.context.body.name, score=score)


@app.route("/api/group/<name>", methods=["GET"])
@api.validate(
    resp=Response(HTTP_200=Resp, HTTP_401=None, validate=False), tags=["api", "test"]
)
def group_score(name):
    score = ["a", "b", "c", "d", "e"]
    return jsonify(name=name, score=score)


@app.route("/api/file", methods=["POST"])
@api.validate(body=MultipartFormRequest(), resp=Response(HTTP_200=DemoModel))
def upload_file():
    files = request.files
    assert files is not None
    return jsonify(uid=1, limit=2, name="success")


api.register(app)


@pytest.fixture(params=[422, 400])
def client(request):
    api.config.VALIDATION_ERROR_CODE = request.param
    with app.test_client() as client:
        yield client


@pytest.mark.parametrize("client", [422], indirect=True)
def test_flask_validate(client):
    resp = client.get("/ping")
    assert resp.status_code == 422
    assert resp.headers.get("X-Error") == "Validation Error"

    resp = client.get("/ping", headers={"lang": "en-US"})
    assert resp.json == {"msg": "pong"}
    assert resp.headers.get("X-Error") is None
    assert resp.headers.get("X-Validation") == "Pass"

    resp = client.post("api/user/flask")
    assert resp.status_code == 422
    assert resp.headers.get("X-Error") == "Validation Error"

    client.set_cookie("flask", "pub", "abcdefg")
    resp = client.post(
        "/api/user/flask?order=1",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json
    assert resp.headers.get("X-Validation") is None
    assert resp.headers.get("X-API") == "OK"
    assert resp.json["name"] == "flask"
    assert resp.json["score"] == sorted(resp.json["score"], reverse=True)

    resp = client.post(
        "/api/user/flask?order=0",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.json["score"] == sorted(resp.json["score"], reverse=False)

    resp = client.post(
        "/api/user/flask",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.json["score"] == sorted(resp.json["score"], reverse=False)

    file = FileStorage(BytesIO(b"abcde"), filename="fileName", name="test.jpg")
    resp = client.post(
        "/api/file",
        data={"fileName": file},
        content_type="content_type='multipart/form-data'",
    )
    assert resp.status_code == 200


@pytest.mark.parametrize("client", [200], indirect=True)
def test_flask_skip_validation(client):
    resp = client.get("api/group/test")
    assert resp.status_code == 200
    assert resp.json["name"] == "test"
    assert resp.json["score"] == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize("client", [422], indirect=True)
def test_flask_doc(client):
    resp = client.get("/apidoc/openapi.json")
    assert resp.json == api.spec

    resp = client.get("/apidoc/redoc")
    assert resp.status_code == 200
    assert b"spec-url='/apidoc/openapi.json'" in resp.data
    assert b"<title>Test API</title>" in resp.data

    resp = client.get("/apidoc/swagger")
    assert resp.status_code == 200


@pytest.mark.parametrize("client", [400], indirect=True)
def test_flask_validate_with_alternative_code(client):
    resp = client.get("/ping")
    assert resp.status_code == 400
    assert resp.headers.get("X-Error") == "Validation Error"

    resp = client.post("api/user/flask")
    assert resp.status_code == 400
    assert resp.headers.get("X-Error") == "Validation Error"
