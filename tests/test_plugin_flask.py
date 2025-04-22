from collections.abc import Callable
from datetime import datetime
from io import BytesIO
import logging
from random import randint
import gzip
from typing import Union
from unittest.mock import ANY

import pytest
import json
from flask import Flask, jsonify, request
from werkzeug.datastructures import FileStorage
from werkzeug.test import Client

from flask_pydantic_spec.types import Response, MultipartFormRequest
from flask_pydantic_spec import FlaskPydanticSpec

from .common import (
    CookiesV1,
    DemoModelV1,
    FileNameV1,
    HeadersV1,
    Query,
    QueryParamsV1,
    QueryV1,
    Resp,
    JSON,
    Headers,
    Cookies,
    DemoModel,
    QueryParams,
    RespV1,
    Users,
    FileName,
    UsersV1,
)


def before_handler(req, resp, err, _):
    if err:
        resp.headers["X-Error"] = "Validation Error"


def after_handler(req, resp, err, _):
    resp.headers["X-Validation"] = "Pass"


def api_after_handler(req, resp, err, _):
    resp.headers["X-API"] = "OK"


api = FlaskPydanticSpec("flask", before=before_handler, after=after_handler, title="Test API")
app = Flask(__name__)


@app.route("/ping")
@api.validate(headers=Headers, tags=["test", "health"], resp=Response(HTTP_200=Resp))
def ping():
    """summary
    description"""
    return _ping()


@app.route("/v1/ping")
@api.validate(headers=HeadersV1, tags=["test", "health"], resp=Response(HTTP_200=RespV1))
def ping_v1():
    """summary
    description"""
    return _ping()


def _ping():
    return jsonify(name="Test", score=[10])


@app.route("/api/user", methods=["GET"])
@api.validate(
    query=QueryParams,
    resp=Response(HTTP_200=Users, HTTP_401=None),
)
def get_users():
    return _get_users()


@app.route("/v1/api/user", methods=["GET"])
@api.validate(
    query=QueryParamsV1,
    resp=Response(HTTP_200=UsersV1, HTTP_401=None),
)
def get_users_v1():
    return _get_users()


def _get_users():
    allowed_names = ["james", "annabel", "bethany"]
    query_params = request.context.query
    return jsonify(
        {
            "data": [
                {"name": name}
                for name in sorted(set(allowed_names).intersection(set(query_params.name)))
            ]
        }
    )


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
    return _user_score(name)


@app.route("/v1/api/user/<name>", methods=["POST"])
@api.validate(
    query=QueryV1,
    body=JSON,
    cookies=CookiesV1,
    resp=Response(HTTP_200=RespV1, HTTP_401=None),
    tags=["api", "test"],
    after=api_after_handler,
)
def user_score_v1(name):
    return _user_score(name)


def _user_score(name):
    score = [randint(0, request.context.body.limit) for _ in range(5)]
    score.sort(reverse=request.context.query.order if request.context.query.order else False)
    assert request.context.cookies.pub == "abcdefg"
    assert request.cookies["pub"] == "abcdefg"
    return jsonify(name=request.context.body.name, score=score)


@app.route("/api/group/<name>", methods=["GET"])
@api.validate(resp=Response(HTTP_200=Resp, HTTP_401=None, validate=False), tags=["api", "test"])
def group_score(name):
    return _group_score(name)


@app.route("/v1/api/group/<name>", methods=["GET"])
@api.validate(resp=Response(HTTP_200=RespV1, HTTP_401=None, validate=False), tags=["api", "test"])
def group_score_v1(name):
    return _group_score(name)


def _group_score(name):
    score = ["a", "b", "c", "d", "e"]
    return jsonify(name=name, score=score)


@app.route("/api/file", methods=["POST"])
@api.validate(body=MultipartFormRequest(model=FileName), resp=Response(HTTP_200=DemoModel))
def upload_file():
    return _upload_file()


@app.route("/v1/api/file", methods=["POST"])
@api.validate(body=MultipartFormRequest(model=FileNameV1), resp=Response(HTTP_200=DemoModelV1))
def upload_file_v1():
    return _upload_file()


def _upload_file():
    files = request.files
    body = request.context.body
    assert body is not None
    assert files is not None
    return jsonify(uid=1, limit=2, name=body.file_name)


api.register(app)


@pytest.fixture(params=[422, 400])
def client(request):
    api.config.VALIDATION_ERROR_CODE = request.param
    with app.test_client() as client:
        yield client


@pytest.fixture(params=[pytest.param("/v1", id="v1"), pytest.param("", id="v2")])
def version(request):
    return request.param


@pytest.mark.parametrize("client", [422], indirect=True)
def test_flask_validate(client: Client, version: str):
    resp = client.get(f"{version}/ping")
    assert resp.status_code == 422
    assert resp.headers.get("X-Error") == "Validation Error"

    resp = client.get(f"{version}/ping", headers={"lang": "en-US"})
    assert resp.json == {"name": "Test", "score": [10]}
    assert resp.headers.get("X-Error") is None
    assert resp.headers.get("X-Validation") == "Pass"

    resp = client.get(
        f"{version}/ping", headers={"lang": "en-US", "Content-Type": "application/json"}
    )
    assert resp.json == {"name": "Test", "score": [10]}
    assert resp.headers.get("X-Error") is None
    assert resp.headers.get("X-Validation") == "Pass"

    resp = client.post(f"{version}/api/user/flask")
    assert resp.status_code == 422
    assert resp.headers.get("X-Error") == "Validation Error"

    client.set_cookie("pub", "abcdefg")
    resp = client.post(
        f"{version}/api/user/flask?order=1",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.json
    assert resp.headers.get("X-Validation") is None
    assert resp.headers.get("X-API") == "OK"
    assert resp.json["name"] == "flask"
    assert resp.json["score"] == sorted(resp.json["score"], reverse=True)

    resp = client.post(
        f"{version}/api/user/flask?order=0",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["score"] == sorted(resp.json["score"], reverse=False)

    resp = client.post(
        f"{version}/api/user/flask",
        data=json.dumps(dict(name="flask", limit=10)),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json["score"] == sorted(resp.json["score"], reverse=False)


@pytest.mark.parametrize("client", [422], indirect=True)
@pytest.mark.parametrize(
    "data",
    [
        lambda: FileStorage(
            BytesIO(json.dumps({"type": "foo", "created_at": str(datetime.now().date())}).encode()),
        ),
        lambda: json.dumps({"type": "foo", "created_at": str(datetime.now().date())}),
    ],
)
def test_sending_file(client: Client, data: Callable[[], Union[FileStorage, str]], version: str):
    file = FileStorage(BytesIO(b"abcde"), filename="test.jpg", name="test.jpg")
    resp = client.post(
        f"{version}/api/file",
        data={
            "file": file,
            "file_name": "another_test.jpg",
            "data": data(),
        },
    )
    assert resp.status_code == 200
    assert resp.json["name"] == "another_test.jpg"


@pytest.mark.parametrize("client", [422], indirect=True)
def test_query_params(client: Client, version: str):
    resp = client.get(f"{version}/api/user?name=james&name=bethany&name=claire")
    assert resp.status_code == 200
    assert len(resp.json["data"]) == 2
    assert resp.json["data"] == [
        {
            "name": "bethany",
        },
        {
            "name": "james",
        },
    ]


@pytest.mark.parametrize("client", [200], indirect=True)
def test_flask_skip_validation(client: Client, version: str):
    resp = client.get(f"{version}/api/group/test")
    assert resp.status_code == 200
    assert resp.json["name"] == "test"
    assert resp.json["score"] == ["a", "b", "c", "d", "e"]


@pytest.mark.parametrize("client", [422], indirect=True)
def test_flask_doc(client: Client):
    resp = client.get("/apidoc/openapi.json")
    assert resp.json == api.spec

    resp = client.get("/apidoc/redoc")
    assert resp.status_code == 200
    assert b"spec-url='/apidoc/openapi.json'" in resp.data
    assert b"<title>Test API</title>" in resp.data

    resp = client.get("/apidoc/swagger")
    assert resp.status_code == 200


@pytest.mark.parametrize("client", [400], indirect=True)
def test_flask_validate_with_alternative_code(client: Client, version: str):
    resp = client.get(f"{version}/ping")
    assert resp.status_code == 400
    assert resp.headers.get("X-Error") == "Validation Error"

    resp = client.post(f"{version}/api/user/flask")
    assert resp.status_code == 400
    assert resp.headers.get("X-Error") == "Validation Error"


@pytest.mark.parametrize("client", [400], indirect=True)
def test_flask_post_gzip(client: Client, version: str):
    body = dict(name="flask", limit=10)
    compressed = gzip.compress(bytes(json.dumps(body), encoding="utf-8"))

    client.set_cookie("pub", "abcdefg")
    resp = client.post(
        f"{version}/api/user/flask?order=0",
        data=compressed,
        headers={
            "content-type": "application/json",
            "content-encoding": "gzip",
        },
    )
    assert resp.status_code == 200
    assert resp.json["name"] == "flask"


@pytest.mark.parametrize("client", [400], indirect=True)
def test_flask_post_gzip_failure(client: Client, version: str):
    body = dict(name="flask")
    compressed = gzip.compress(bytes(json.dumps(body), encoding="utf-8"))

    client.set_cookie("pub", "abcdefg")
    resp = client.post(
        f"{version}/api/user/flask?order=0",
        data=compressed,
        headers={
            "content-type": "application/json",
            "content-encoding": "gzip",
        },
    )
    assert resp.status_code == 400
    assert resp.json == [
        {
            "input": {"name": "flask"},
            "loc": ["limit"],
            "msg": "Field required",
            "type": "missing",
            "url": ANY,
        }
    ]


api2 = FlaskPydanticSpec("flask")
app2 = Flask(__name__)


@pytest.fixture
def client2():
    with app2.test_client() as client:
        yield client


@app2.post("/create")
@api2.validate(body=DemoModel, resp=Response(HTTP_200=Resp, HTTP_401=None))
def valid_response():
    return jsonify(name=request.context.body.name)


def test_default_before_handler(client2: Client, caplog):
    with caplog.at_level(logging.INFO):
        resp = client2.post("/create")

    assert resp.status_code == 422
    assert "Validation Error" in caplog.text


def test_default_after_handler(client2: Client, caplog):
    with caplog.at_level(logging.INFO):
        resp = client2.post("/create", json=dict(uid=1, limit=1, name="name"))

    assert resp.status_code == 500
    assert "500 Response Validation Error" in caplog.text
