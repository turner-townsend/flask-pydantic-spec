from datetime import date
from enum import IntEnum, Enum
from typing import List, Optional

from pydantic import BaseModel, root_validator


class Order(IntEnum):
    asce = 1
    desc = 0


class Query(BaseModel):
    order: Optional[Order]


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


class Headers(BaseModel):
    lang: Language

    @root_validator(pre=True)
    def lower_keys(cls, values):
        return {key.lower(): value for key, value in values.items()}


class Cookies(BaseModel):
    pub: str


class DemoModel(BaseModel):
    uid: int
    limit: int
    name: str


def get_paths(spec):
    paths = []
    for path in spec["paths"]:
        if spec["paths"][path]:
            paths.append(path)

    paths.sort()
    return paths


class HistoryDate(BaseModel):
    date: date
