from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    generation_prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    join_code: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    initial_count: Mapped[int] = mapped_column(Integer, default=30)
    refill_threshold: Mapped[int] = mapped_column(Integer, default=10)
    min_answers: Mapped[int] = mapped_column(Integer, default=20)
    ema_threshold: Mapped[str] = mapped_column(String(40), default="0.8")
    alpha: Mapped[str] = mapped_column(String(40), default="0.2")
    default_absolute_tolerance: Mapped[str] = mapped_column(String(40), default="0")
    default_relative_tolerance: Mapped[str] = mapped_column(String(40), default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    questions: Mapped[list["Question"]] = relationship(cascade="all, delete-orphan")
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str] = mapped_column(String(100))
    absolute_tolerance: Mapped[str] = mapped_column(String(40), default="0")
    relative_tolerance: Mapped[str] = mapped_column(String(40), default="0")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    current_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    answer_count: Mapped[int] = mapped_column(Integer, default=0)
    ema: Mapped[str | None] = mapped_column(String(40))
    achieved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    exercise: Mapped[Exercise] = relationship(back_populates="participants")
    answers: Mapped[list["Answer"]] = relationship(cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    submitted_answer: Mapped[str] = mapped_column(String(100))
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    question: Mapped[Question] = relationship()


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), index=True)
    requested_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
