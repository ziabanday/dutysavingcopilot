# app/core/json_safety.py
from __future__ import annotations

import json
from typing import Tuple, Type

from pydantic import BaseModel, ValidationError


def try_parse_and_validate(model: Type[BaseModel], text: str) -> Tuple[BaseModel | None, str | None]:
    """
    Return (instance, error_message). If parse+validate ok, error_message is None.
    """
    try:
        data = json.loads(text)
    except Exception as e:
        return None, f"JSON parse error: {e}"
    try:
        inst = model.model_validate(data)
        return inst, None
    except ValidationError as ve:
        return None, f"Validation error: {ve}"


def format_fix_prompt(schema_json: dict, bad_text: str) -> str:
    return (
        "Return only valid JSON that matches this schema. Do not add prose.\n\n"
        "SCHEMA:\n"
        f"{schema_json}\n\n"
        "BAD_JSON:\n"
        f"{bad_text}\n"
    )
