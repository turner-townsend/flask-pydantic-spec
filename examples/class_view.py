from flask import Flask, request, jsonify
from pydantic import BaseModel, Field, Extra
from flask_pydantic_spec import FlaskPydanticSpec, Response, Request
import time

from flask.views import MethodView


class ExampleQueryGetRequest(BaseModel):
    text: str = Field(default="default query strings", description="blabla")

    class Config:
        extra = Extra.forbid


class ExampleQueryPostRequest(BaseModel):
    query_text: str = Field(default="default query strings", description="post req blabla")

    class Config:
        extra = Extra.forbid


class ExampleQueryGetResponse(BaseModel):
    my_get_time: int = Field(description="current time")

    class Config:
        extra = Extra.forbid


class ExamplePathResponse(BaseModel):
    id: str = Field(description="id")
    current_time: int = Field(description="current time")
    query_text: str = Field(default="", description="query text")

    class Config:
        extra = Extra.forbid


app = Flask(__name__)
api = FlaskPydanticSpec("flask")


class TestQueryView(MethodView):
    """
    Test view class
    """

    @api.validate(
        query=ExampleQueryGetRequest,
        resp=Response(HTTP_200=ExampleQueryGetResponse),
        tags=["test query"],
    )
    def get(self):
        """
        Test query get view
        :return:
        """
        return jsonify({"my_get_time": int(time.time())})

    @api.validate(query=ExampleQueryPostRequest, tags=["test query"])
    def post(self):
        """
        Test query post view
        :return:
        """
        return jsonify(
            {"post_time": int(time.time()), "post_text": request.context.query.query_text}
        )


class TestPathView(MethodView):
    @api.validate(
        query=ExampleQueryPostRequest,
        resp=Response(HTTP_200=ExamplePathResponse),
        tags=["test path"],
    )
    def post(self, id):
        """
        Test path post view
        :return:
        """
        print(f"query: {request.context.query}")
        return jsonify(
            ExamplePathResponse(
                id=id, current_time=int(time.time()), query_text=request.args["text"]
            ).dict()
        )


class TestBodyView(MethodView):
    @api.validate(
        body=Request(ExampleQueryPostRequest),
        resp=Response(HTTP_200=ExamplePathResponse),
        tags=["test body"],
    )
    def post(self, id):
        """
        Test body post view
        :return:
        """
        return jsonify({"id": id, "current_time": int(time.time())})


if __name__ == "__main__":
    api.register(app)  # if you don't register in api init step
    app.add_url_rule(
        "/api/testquery", methods=["GET", "POST"], view_func=TestQueryView.as_view("TestQueryView"),
    )
    api.register_class_view_apidoc(TestQueryView)

    app.add_url_rule(
        "/api/testpath/<id>", methods=["POST"], view_func=TestPathView.as_view("TestPathView"),
    )
    api.register_class_view_apidoc(TestPathView)

    app.add_url_rule(
        "/api/testbody/<id>", methods=["POST"], view_func=TestBodyView.as_view("TestBodyView"),
    )
    api.register_class_view_apidoc(TestBodyView)

    app.run(port=8000)
