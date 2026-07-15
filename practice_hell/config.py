from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


JOIN_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class Choice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)


class NumberQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_type: Literal["number"]
    absolute_tolerance: str = "0"
    relative_tolerance: str = "0"

    @field_validator("absolute_tolerance", "relative_tolerance")
    @classmethod
    def validate_tolerance(cls, value: str) -> str:
        try:
            parsed = Decimal(value)
        except InvalidOperation:
            raise ValueError("許容誤差は数値文字列にしてください") from None
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("許容誤差は0以上の有限値にしてください")
        return str(parsed)


class SingleChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_type: Literal["single_choice"]
    choices: list[Choice] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_unique_choices(self) -> "SingleChoiceQuestion":
        ids = [choice.id for choice in self.choices]
        if len(ids) != len(set(ids)):
            raise ValueError("選択肢IDが重複しています")
        return self


QuestionConfig = Annotated[
    NumberQuestion | SingleChoiceQuestion,
    Field(discriminator="answer_type"),
]


class GenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)


class MasteryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_size: int = Field(gt=0, le=1000)
    required_accuracy_percent: int = Field(ge=0, le=100)


class ProblemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    join_code: str
    title: str = Field(min_length=1, max_length=200)
    generation: GenerationConfig
    question: QuestionConfig
    mastery: MasteryConfig

    @field_validator("join_code")
    @classmethod
    def validate_join_code(cls, value: str) -> str:
        if not JOIN_CODE_PATTERN.fullmatch(value):
            raise ValueError(
                "join_codeは英数字で始まる64文字以内の英数字・ハイフン・アンダースコアにしてください"
            )
        return value


def load_problems(directory: Path) -> dict[str, ProblemConfig]:
    problems: dict[str, ProblemConfig] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            problem = ProblemConfig.model_validate(raw)
        except Exception as exc:
            raise RuntimeError(f"問題YAMLが不正です: {path}: {exc}") from exc
        if problem.join_code in problems:
            raise RuntimeError(f"join_codeが重複しています: {problem.join_code}")
        problems[problem.join_code] = problem
    if not problems:
        raise RuntimeError(f"問題YAMLがありません: {directory}")
    return problems
