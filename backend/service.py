from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Answer, Exercise, Participant, Question


def parse_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("有効な数値を入力してください") from None
    if not parsed.is_finite():
        raise ValueError("有限の数値を入力してください")
    return parsed


def is_correct(submitted: Decimal, question: Question) -> bool:
    expected = parse_decimal(question.expected_answer)
    absolute = parse_decimal(question.absolute_tolerance)
    relative = parse_decimal(question.relative_tolerance)
    tolerance = max(absolute, relative * abs(expected))
    return abs(submitted - expected) <= tolerance


def update_progress(participant: Participant, correct: bool) -> None:
    alpha = parse_decimal(participant.exercise.alpha)
    result = Decimal(1 if correct else 0)
    old_ema = parse_decimal(participant.ema) if participant.ema is not None else None
    ema = result if old_ema is None else alpha * result + (Decimal(1) - alpha) * old_ema
    participant.answer_count += 1
    participant.ema = str(ema)
    participant.achieved = (
        participant.answer_count >= participant.exercise.min_answers
        and ema >= parse_decimal(participant.exercise.ema_threshold)
    )


def next_question(db: Session, participant: Participant) -> Question:
    answered_ids = select(Answer.question_id).where(Answer.participant_id == participant.id)
    question = db.scalar(
        select(Question)
        .where(
            Question.exercise_id == participant.exercise_id,
            Question.status == "approved",
            Question.id.not_in(answered_ids),
        )
        .order_by(func.random())
        .limit(1)
    )
    if question:
        return question

    last_question_id = db.scalar(
        select(Answer.question_id)
        .where(Answer.participant_id == participant.id)
        .order_by(Answer.id.desc())
        .limit(1)
    )
    query = select(Question).where(
        Question.exercise_id == participant.exercise_id,
        Question.status == "approved",
    )
    if last_question_id is not None:
        query = query.where(Question.id != last_question_id)
    question = db.scalar(query.order_by(func.random()).limit(1))
    if question is None and last_question_id is not None:
        question = db.get(Question, last_question_id)
    if question is None:
        raise HTTPException(409, "承認済みの問題がありません")
    return question


def create_join_code(db: Session) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if db.scalar(select(Exercise).where(Exercise.join_code == code)) is None:
            return code
    raise RuntimeError("参加コードを生成できませんでした")
