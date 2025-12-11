from datetime import date
from enum import Enum, IntEnum

from pydantic import BaseModel, model_validator, v1
from werkzeug.routing import BaseConverter


class Order(IntEnum):
    asce = 1
    desc = 0


class Query(BaseModel):
    order: Order | None = None


class QueryParams(BaseModel):
    name: list[str] | None = None


class User(BaseModel):
    name: str


class Users(BaseModel):
    data: list[User]


class JSON(BaseModel):
    name: str
    limit: int


class Resp(BaseModel):
    name: str
    score: list[int]


class Language(str, Enum):
    en = "en-US"
    zh = "zh-CN"


class Headers(BaseModel):
    lang: Language

    @model_validator(mode="before")
    def lower_keys(cls, values):
        return {key.lower(): value for key, value in values.items()}


class Cookies(BaseModel):
    pub: str


class DemoModel(BaseModel):
    uid: int
    limit: int
    name: str


class FileMetadata(BaseModel):
    type: str
    created_at: date


class FileName(BaseModel):
    file_name: str
    data: FileMetadata


class ExampleEnum(Enum):
    one = "one"
    two = "two"


class ExampleConverter(BaseConverter):
    def to_python(self, value) -> ExampleEnum:
        return ExampleEnum(value)

    def to_url(self, value) -> str:
        return value.value


class UnknownConverter(BaseConverter):
    def to_python(self, value) -> object:
        return object()

    def to_url(self, value) -> str:
        return str(value)


class QueryV1(v1.BaseModel):
    order: Order | None = None


class QueryParamsV1(v1.BaseModel):
    name: list[str] | None = None


class UserV1(v1.BaseModel):
    name: str


class UsersV1(v1.BaseModel):
    data: list[UserV1]


class JSONV1(v1.BaseModel):
    name: str
    limit: int


class RespV1(v1.BaseModel):
    name: str
    score: list[int]


class HeadersV1(v1.BaseModel):
    lang: Language

    @v1.root_validator(pre=True)
    def lower_keys(cls, values):
        return {key.lower(): value for key, value in values.items()}


class CookiesV1(v1.BaseModel):
    pub: str


class DemoModelV1(v1.BaseModel):
    uid: int
    limit: int
    name: str


class FileMetadataV1(v1.BaseModel):
    type: str
    created_at: date


class FileNameV1(v1.BaseModel):
    file_name: str
    data: FileMetadataV1


def get_paths(spec):
    paths = []
    for path in spec["paths"]:
        if spec["paths"][path]:
            paths.append(path)

    paths.sort()
    return paths
