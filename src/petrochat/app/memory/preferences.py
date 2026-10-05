"""Small explicit preference vocabulary; no semantic similarity based overwrite."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field, model_validator


class Preference(BaseModel):
    scope: str = Field(default="global", min_length=1, max_length=64)
    key: str
    value: str
    unit: str = ""

    @model_validator(mode="after")
    def validate_value(self):
        if self.key == "query.default_tonnage":
            try:
                amount = Decimal(self.value)
            except InvalidOperation as exc:
                raise ValueError("tonnage must be numeric") from exc
            if not amount.is_finite() or amount <= 0 or amount > 10**12 or self.unit != "吨":
                raise ValueError("tonnage must be positive tonnes")
            self.value = format(amount.normalize(), "f")
        elif self.key == "answer.verbosity":
            if self.value not in {"concise", "detailed"} or self.unit:
                raise ValueError("invalid verbosity")
        else:
            raise ValueError("unsupported preference key")
        return self

    def content(self) -> str:
        if self.key == "query.default_tonnage":
            return f"{self.scope}：默认查询吨位为{self.value}吨。"
        return f"{self.scope}：回答偏好为{'简洁' if self.value == 'concise' else '详细'}。"


def explicit_preference(question: str) -> Preference | None:
    """Only complete single-intent templates. Ambiguous/project prose falls through.

    Never infer a user's preference from an assistant answer, negation or a
    multi-clause sentence. More complex preferences use the explicit API.
    """
    value = re.sub(r"[。！!\s]+$", "", question.strip())
    number = re.fullmatch(r"(?:以后|今后)?默认(?:查询|查)?(?:吨位为)?([0-9]+(?:\.[0-9]+)?)(万)?吨(?:的任务)?", value)
    if number:
        amount = Decimal(number[1]) * (10000 if number[2] else 1)
        return Preference(key="query.default_tonnage", value=str(amount), unit="吨")
    if re.fullmatch(r"(?:请记住[，,：:]?)?(?:以后|今后)?(?:回答|回复)(?:请)?(?:简洁|简短)(?:一点)?", value):
        return Preference(key="answer.verbosity", value="concise")
    if re.fullmatch(r"(?:请记住[，,：:]?)?(?:以后|今后)?(?:回答|回复)(?:请)?详细(?:一点)?", value):
        return Preference(key="answer.verbosity", value="detailed")
    return None
