"""Visualization-independent API types. All spans are half-open character ranges."""
from pydantic import BaseModel, Field


class SourceSpan(BaseModel):
    start: int
    end: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int


class AnatomyNode(BaseModel):
    id: str
    kind: str
    label: str
    explanation: str
    relationship: str
    span: SourceSpan
    value: str | int | float | bool | None = None
    overview: list[str] = Field(default_factory=list)
    children: list['AnatomyNode'] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    source: str = Field(min_length=1, max_length=10000)


class Connection(BaseModel):
    source_id: str
    target_id: str
    label: str


class Anatomy(BaseModel):
    schema_version: str = '0.5'
    source: str
    root: AnatomyNode

    connections: list[Connection] = Field(default_factory=list)
