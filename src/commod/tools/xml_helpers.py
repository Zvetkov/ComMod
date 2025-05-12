from enum import Enum
from typing import Annotated

from lxml import objectify
from pydantic import BaseModel, Field, model_validator


class ActionType(Enum):
    ADD = "Add"
    REPLACE = "Replace"
    ADD_OR_REPLACE = "AddOrReplace"
    MODIFY = "Modify"
    MODIFY_OR_FAIL = "ModifyOrFail"
    REMOVE = "Remove"
    REMOVE_OR_FAIL = "RemoveOrFail"

    @classmethod
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]


class Command(BaseModel, arbitrary_types_allowed = True):
    action: ActionType
    parent_path: str
    selector: str
    tag: str
    node_attrs: dict
    selector_keys: list[str]
    children_nodes: list[objectify.ObjectifiedElement] | None = Field(repr=False)
    merge_author: str = ""
    existing_count: Annotated[int, Field(ge=1, le=50)] = 1
    desired_count: Annotated[int, Field(ge=1, le=50)] = 1
    source_node: objectify.ObjectifiedElement | None = Field(default=None, repr=False)
    modded_node: objectify.ObjectifiedElement | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def check_selector(self) -> "Command":
        if not self.selector and not self.selector_keys:
            raise ValueError(f"Merge command must specify either _SelectorKeys or _Selector:\n\n{self!r}")
        return self


class InvalidMergeCommandError(Exception):
    def __init__(self, error_desc: str | None = None) -> None:
        self.error_desc = error_desc
        super().__init__(self.error_desc)


class AmbiguousMergeCommandError(Exception):
    ...