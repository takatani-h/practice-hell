from __future__ import annotations

from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TeacherLogin(BaseModel):
    password: str


class ExerciseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    generation_prompt: str = Field(min_length=1, max_length=4000)
    initial_count: int = Field(default=30, ge=1, le=100)
    refill_threshold: int = Field(default=10, ge=1, le=100)
    min_answers: int = Field(default=20, ge=1, le=1000)
    ema_threshold: str = "0.8"
    alpha: str = "0.2"
    default_absolute_tolerance: str = "0"
    default_relative_tolerance: str = "0"


class QuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    expected_answer: str | None = None
    absolute_tolerance: str | None = None
    relative_tolerance: str | None = None
    status: str | None = None


class JoinRequest(BaseModel):
    join_code: str = Field(min_length=4, max_length=12)
    display_name: str = Field(min_length=1, max_length=80)


class SubmitAnswer(BaseModel):
    question_id: int
    answer: str = Field(min_length=1, max_length=100)


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    expected_answer: str
    absolute_tolerance: str = "0"
    relative_tolerance: str = "0"

    @field_validator("expected_answer", "absolute_tolerance", "relative_tolerance")
    @classmethod
    def validate_decimal(cls, value: str) -> str:
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, AttributeError):
            raise ValueError("有効な数値を指定してください") from None
        if not parsed.is_finite():
            raise ValueError("有限の数値を指定してください")
        return str(parsed)


class GeneratedQuestionList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestion]
