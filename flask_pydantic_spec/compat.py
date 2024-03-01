from pydantic import VERSION as PYDANTIC_VERSION, BaseModel
from pydantic.fields import FieldInfo
import typing as t


FieldInfo
T = t.TypeVar("T", bound=BaseModel)

IS_PYDANTIC_2 = PYDANTIC_VERSION.startswith("2.")

if IS_PYDANTIC_2:

    def model_validate(model: t.Type[T], data: t.Any) -> T:
        return model.model_validate(data)

    def model_json_schema(model: BaseModel, **kwargs: t.Any) -> t.Dict[str, t.Any]:
        return model.model_json_schema(**kwargs)

    def model_fields(model: BaseModel) -> t.Dict[str, FieldInfo]:
        return model.model_fields

else:

    def model_validate(model: t.Type[T], data: t.Any) -> T:
        return model.parse_obj(data)

    def model_json_schema(model: BaseModel, **kwargs: t.Any) -> t.Dict[str, t.Any]:
        return model.schema(**kwargs)

    def model_fields(model: BaseModel) -> t.Dict[str, FieldInfo]:
        return model.__fields__
