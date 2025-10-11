from dataclasses import dataclass
from typing import Optional


@dataclass
class ArgInfo:
    name: str
    annotation: Optional[str]
    has_default: bool

@dataclass
class FunctionInfo:
    name: str
    qualname: str
    kind: str
    visibility: str
    async_: bool
    decorators: list[str]
    returns: Optional[str]
    args: list[ArgInfo]
    docstring: Optional[str]
    loc: dict[str, Optional[int]]
    nested_functions: list["FunctionInfo"]

@dataclass
class VariableInfo:
    target: str
    annotation: Optional[str]
    value_preview: Optional[str]
    scope: str
    loc: dict[str, Optional[int]]

@dataclass
class ClassInfo:
    name: str
    qualname: str
    visibility: str
    bases: list[str]
    decorators: list[str]
    docstring: Optional[str]
    loc: dict[str, Optional[int]]
    class_attributes: list[VariableInfo]
    instance_attributes: list[VariableInfo]
    methods: list[FunctionInfo]