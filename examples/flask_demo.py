from flask import Flask, request, jsonify, abort
from pydantic import BaseModel, Field
from random import random
from enum import Enum

from flask_pydantic_spec import FlaskPydanticSpec, Response


app = Flask(__name__)
api = FlaskPydanticSpec("flask")


class Query(BaseModel):
    text: str = "default query strings"


class Resp(BaseModel):
    label: int
    score: float = Field(
        ...,
        gt=0,
        lt=1,
    )


class Data(BaseModel):
    uid: str
    limit: int = 5
    vip: bool

    class Config:
        json_schema_extra = {
            "example": {
                "uid": "very_important_user",
                "limit": 10,
                "vip": True,
            }
        }


class Language(str, Enum):
    en = "en-US"
    zh = "zh-CN"


class Header(BaseModel):
    Lang: Language


class Cookie(BaseModel):
    key: str


@app.route("/api/predict/<string(length=2):source>/<string(length=2):target>", methods=["POST"])
@api.validate(query=Query, body=Data, resp=Response("HTTP_403", HTTP_200=Resp), tags=["model"])
def predict(source, target):
    """
    predict demo

    demo for `query`, `data`, `resp`, `x`

    query with ``http POST ':8000/api/predict/zh/en?text=hello' uid=xxx limit=5 vip=false ``
    """
    print(f"=> from {source} to {target}")  # path
    print(f"JSON: {request.context.body}")  # Data
    print(f"Query: {request.context.query}")  # Query
    if random() < 0.5:
        abort(403)

    return jsonify(label=int(10 * random()), score=random())


@app.route("/api/header", methods=["POST"])
@api.validate(headers=Header, cookies=Cookie, resp=Response("HTTP_203"), tags=["test", "demo"])
def with_code_header():
    """
    demo for JSON with status code and header

    query with ``http POST :8000/api/header Lang:zh-CN Cookie:key=hello``
    """
    return jsonify(language=request.context.headers.Lang), 203, {"X": 233}


if __name__ == "__main__":
    api.register(app)
    app.run(port=8000)
