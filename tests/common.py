from datetime import date
from enum import IntEnum, Enum
from typing import List, Optional

from pydantic import BaseModel
from flask_pydantic_spec.compat import IS_PYDANTIC_2
from werkzeug.routing import BaseConverter


class Order(IntEnum):
    asce = 1
    desc = 0


class Query(BaseModel):
    order: Optional[Order] = None


class QueryParams(BaseModel):
    name: Optional[List[str]]


class User(BaseModel):
    name: str


class Users(BaseModel):
    data: List[User]


class JSON(BaseModel):
    name: str
    limit: int


class Resp(BaseModel):
    name: str
    score: List[int]


class Language(str, Enum):
    en = "en-US"
    zh = "zh-CN"


if IS_PYDANTIC_2:
    from pydantic import model_validator

    class Headers(BaseModel):
        lang: Language

        @model_validator(mode="before")
        @classmethod
        def lower_keys(cls, values):
            return {key.lower(): value for key, value in values.items()}

else:
    from pydantic import root_validator

    class Headers(BaseModel):
        lang: Language

        @root_validator(pre=True, allow_reuse=True)
        def lower_keys(cls, values):
            return {key.lower(): value for key, value in values.items()}


class Cookies(BaseModel):
    pub: List[str]


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


def get_paths(spec):
    paths = []
    for path in spec["paths"]:
        if spec["paths"][path]:
            paths.append(path)

    paths.sort()
    return paths
