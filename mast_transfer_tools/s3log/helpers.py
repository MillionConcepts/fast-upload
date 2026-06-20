import datetime as dt
from types import NoneType
from typing import TypedDict

import yaml


LOG_FIELD_SPEC = (
    {"name": "time", "required": True},
    {"name": "category", "required": True},
    {"name": "ref", "required": True},
    {"name": "status", "required": True},
    {"name": "message", "required": False},
    {"name": "agent_id", "required": True},
)
"""Column layout of TSV logs."""


class LogFieldRec(TypedDict):
    """Specification for an individual log field."""
    name: str
    required: bool


def timestamp() -> str:
    """create UTC timestamp at millisecond precision"""
    return f"{dt.datetime.now(dt.UTC).isoformat()[:23]}Z"


def yamldump_nested(d: dict) -> dict:
    """Return a version of `d` with 'complicated' values serialized to YAML."""
    out = {}
    for k, v in d.items():
        if isinstance(v, (str, int, float, NoneType)):
            out[k] = v
        else:
            out[k] = yaml.dump(v)
    return out
